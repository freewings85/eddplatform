"""RunTaskWorkflow 逐 case 分派 child workflow（名/队列=eval_code）——方案 A 契约测试。

打真本地 Temporal dev server（localhost:7233，docker 容器 `temporal`）；
不可达则 skip（受限网络下 time-skipping 测试服务器二进制下载不动，故不用它）。
"""
import socket
import uuid

import pytest
from temporalio import workflow
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from eddplatform.runtime.temporal.shared import (TASK_QUEUE, CaseResultOut, CaseSpec,
                                                 RunCaseInput, RunTaskInput)
from eddplatform.runtime.temporal.workflows import RunTaskWorkflow

TEMPORAL = "localhost:7233"


def _temporal_up() -> bool:
    try:
        s = socket.create_connection(("127.0.0.1", 7233), timeout=2)
        s.close()
        return True
    except OSError:
        return False


@workflow.defn(name="demo-eval", sandboxed=False)
class FakeEvalWorkflow:
    @workflow.run
    async def run(self, inp: RunCaseInput) -> CaseResultOut:
        if inp.case.case_id == "bad":
            # 评估程序契约：判定/执行失败抛 ApplicationError（普通异常只会让
            # workflow task 无限重试，不会把失败传回平台）
            raise ApplicationError("判定失败", non_retryable=True)
        return CaseResultOut(case_id=inp.case.case_id, status="passed",
                             scores={"judge": 1.0}, metrics={"latency_s": 0.1})


@pytest.mark.asyncio
async def test_dispatch_cases_to_eval_code_queue():
    if not _temporal_up():
        pytest.skip("Temporal dev server 不可达（localhost:7233）")
    client = await Client.connect(TEMPORAL)
    inp = RunTaskInput(preconditions=[], namespace="ns", run_id="R-1",
                       eval_code="demo-eval",
                       cases=[CaseSpec(case_id="c1", name="用例1", inputs="你好"),
                              CaseSpec(case_id="bad", name="坏用例")])
    async with Worker(client, task_queue=TASK_QUEUE, workflows=[RunTaskWorkflow]):
        async with Worker(client, task_queue="demo-eval", workflows=[FakeEvalWorkflow]):
            out = await client.execute_workflow(
                RunTaskWorkflow.run, inp,
                id=f"test-dispatch-{uuid.uuid4().hex[:8]}", task_queue=TASK_QUEUE)
    assert out.status == "up"
    by_id = {c.case_id: c for c in out.case_results}
    assert by_id["c1"].status == "passed" and by_id["c1"].scores == {"judge": 1.0}
    assert by_id["bad"].status == "error" and "判定失败" in by_id["bad"].detail
