"""执行一次 task：组 RunTaskInput → 异步 start workflow → 后台回写 RunRecord。"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import timedelta

from temporalio.client import Client

from eddplatform.domain.models import Case, CaseRunResult, RunRecord, RunStatus, Task
from eddplatform.runtime.temporal.shared import TASK_QUEUE, CaseSpec, RunTaskInput, to_spec
from eddplatform.store.run_store import RunStore

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def _connect(address: str) -> Client:
    return await Client.connect(address)


def _namespace(system_id: str, run_id: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", f"edd-{system_id}-{run_id}".lower()).strip("-")


def case_to_spec(case: Case) -> CaseSpec:
    return CaseSpec(
        case_id=case.id, name=case.name, code=case.code,
        inputs=case.inputs if isinstance(case.inputs, str)
        else json.dumps(case.inputs, ensure_ascii=False),
        expected=(case.expected_output
                  if isinstance(case.expected_output, str) or case.expected_output is None
                  else json.dumps(case.expected_output, ensure_ascii=False)),
        metadata=dict(case.metadata),
    )


async def start_run(system_id: str, task: Task, *, eval_code: str | None,
                    cases: list[CaseSpec], run_store: RunStore) -> RunRecord:
    """提交执行。Temporal 连不上抛 ConnectionError（API 层转 503），不留运行记录。"""
    try:
        client = await _connect(TEMPORAL_ADDRESS)
    except Exception as e:  # noqa: BLE001 —— 连接失败统一视为不可达
        raise ConnectionError(f"Temporal server 未启动（{TEMPORAL_ADDRESS}）: {e}")

    run = run_store.create(RunRecord(system_id=system_id, task_id=task.id, task_name=task.name))
    inp = RunTaskInput(
        preconditions=[to_spec(pc) for pc in task.preconditions],
        namespace=_namespace(system_id, run.id),
        eval_deploy=None,
        eval_target=None,
        run_id=run.id,
        eval_code=eval_code,
        cases=cases,
    )
    handle = await client.start_workflow(
        "RunTaskWorkflow", inp, id=f"edd-run-{run.id}", task_queue=TASK_QUEUE,
        execution_timeout=timedelta(minutes=30),
    )
    run.workflow_id = f"edd-run-{run.id}"
    run.namespace = inp.namespace
    run_store.update(run)
    asyncio.get_running_loop().create_task(_watch(handle, run.id, run_store))
    return run


async def _watch(handle, run_id: str, run_store: RunStore) -> None:
    try:
        out = await handle.result()
        for cr in getattr(out, "case_results", None) or []:
            d = cr if isinstance(cr, dict) else cr.__dict__
            run_store.add_case_result(run_id, CaseRunResult(
                case_id=d.get("case_id", ""), status=d.get("status", "error"),
                scores=d.get("scores") or {}, metrics=d.get("metrics") or {},
                detail=d.get("detail", ""), trace_url=d.get("trace_url")))
        status = RunStatus.SUCCEEDED if out.status == "up" else RunStatus.FAILED
        run_store.finish(run_id, status, versions=out.versions,
                         outcomes=[o if isinstance(o, dict) else o.__dict__ for o in out.outcomes],
                         detail="" if out.status == "up" else "前置条件失败，见 outcomes")
    except Exception as e:  # noqa: BLE001 —— workflow 失败/超时都归 FAILED
        run_store.finish(run_id, RunStatus.FAILED, detail=str(e))
