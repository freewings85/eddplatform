"""执行一次 task：组 RunTaskInput → 异步 start workflow → 后台回写 RunRecord。"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import timedelta

from temporalio.client import Client

from eddplatform.domain.models import CaseRunResult, RunRecord, RunStatus, Task
from eddplatform.runtime.temporal.shared import (TASK_QUEUE, CaseGroup,
                                                 RunTaskInput, RunTaskOutput,
                                                 to_spec)
from eddplatform.store.run_log_store import RunLogStore
from eddplatform.store.run_store import RunStore

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def _connect(address: str) -> Client:
    return await Client.connect(address)


def _namespace(system_id: str, run_id: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", f"edd-{system_id}-{run_id}".lower()).strip("-")


async def start_run(system_id: str, task: Task, *,
                    case_groups: list[CaseGroup] | None = None,
                    run_store: RunStore) -> RunRecord:
    """提交执行。Temporal 连不上抛 ConnectionError（API 层转 503），不留运行记录。"""
    try:
        client = await _connect(TEMPORAL_ADDRESS)
    except Exception as e:  # noqa: BLE001 —— 连接失败统一视为不可达
        raise ConnectionError(f"Temporal server 未启动（{TEMPORAL_ADDRESS}）: {e}")

    groups = [g for g in (case_groups or []) if g.cases]
    run = run_store.create(RunRecord(system_id=system_id, task_id=task.id, task_name=task.name))
    inp = RunTaskInput(
        preconditions=[to_spec(pc) for pc in task.preconditions],
        namespace=_namespace(system_id, run.id),
        eval_deploy=None,
        eval_target=None,
        run_id=run.id,
        case_groups=groups,
        destroy=bool(getattr(task, "destroy_after", False)),
        runs_per_case=max(1, int(getattr(task, "runs_per_case", 1) or 1)),
        case_concurrency=max(1, int(getattr(task, "case_concurrency", 4) or 4)),
    )
    handle = await client.start_workflow(
        "RunTaskWorkflow", inp, id=f"edd-run-{run.id}", task_queue=TASK_QUEUE,
        execution_timeout=timedelta(minutes=30),
        result_type=RunTaskOutput,     # 按名字启动时不给类型会拿到裸 dict
    )
    run.workflow_id = f"edd-run-{run.id}"
    run.namespace = inp.namespace
    run_store.update(run)
    parts = "、".join(f"{g.dataset}({len(g.cases)})" for g in groups) or "—"
    _log(run_store, run.id,
         f"RUN {run.id} 已提交 · 任务「{task.name}」 · workflow {run.workflow_id} · "
         f"namespace {inp.namespace} · 用例 {sum(len(g.cases) for g in groups)} 条"
         f"{f' × {inp.runs_per_case} 次' if inp.runs_per_case > 1 else ''}"
         f" · 分组 {parts}")
    asyncio.get_running_loop().create_task(_watch(handle, run.id, run_store))
    return run


def _log(run_store: RunStore, run_id: str, line: str) -> None:
    """API 侧的控制台日志（提交/收尾），尽力而为。"""
    try:
        RunLogStore(run_store.db).append(run_id, line)
    except Exception:  # noqa: BLE001 —— 日志失败不影响执行
        pass


async def _watch(handle, run_id: str, run_store: RunStore) -> None:
    try:
        out = await handle.result()
        stats: dict[str, int] = {}
        for cr in getattr(out, "case_results", None) or []:
            d = cr if isinstance(cr, dict) else cr.__dict__
            status_s = d.get("status", "error")
            stats[status_s] = stats.get(status_s, 0) + 1
            run_store.add_case_result(run_id, CaseRunResult(
                case_id=d.get("case_id", ""), status=status_s,
                scores=d.get("scores") or {}, metrics=d.get("metrics") or {},
                detail=d.get("detail", ""), trace_url=d.get("trace_url"),
                report=d.get("report") or "", program=d.get("program") or "",
                dataset=d.get("dataset") or "",
                attempts=int(d.get("attempts") or 1),
                passed_attempts=int(d.get("passed_attempts") or 0)))
        status = RunStatus.SUCCEEDED if out.status == "up" else RunStatus.FAILED
        run_store.finish(run_id, status, versions=out.versions,
                         outcomes=[o if isinstance(o, dict) else o.__dict__ for o in out.outcomes],
                         case_stats=stats,
                         detail="" if out.status == "up" else "执行失败，见 outcomes")
        _log(run_store, run_id,
             f"=== RUN {run_id} 结束: {status.value} · 用例统计 {stats or '—'} · "
             f"版本 {out.versions or '—'} ===")
    except Exception as e:  # noqa: BLE001 —— workflow 失败/超时都归 FAILED
        run_store.finish(run_id, RunStatus.FAILED, detail=str(e))
        _log(run_store, run_id, f"=== RUN {run_id} 结束: failed · {e} ===")
