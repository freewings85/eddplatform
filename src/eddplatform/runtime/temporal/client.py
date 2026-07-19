"""EDD 侧提交入口：启动一个 task = 把参数传给 Temporal，拉起 RunTaskWorkflow。"""

from __future__ import annotations

import os
from datetime import timedelta

from temporalio.client import Client

from eddplatform.runtime.temporal.shared import TASK_QUEUE, RunTaskInput, RunTaskOutput
from eddplatform.runtime.temporal.workflows import RunTaskWorkflow

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def run_task(
    inp: RunTaskInput, *, workflow_id: str, address: str | None = None
) -> RunTaskOutput:
    """提交一次 task 执行并等待结果（EDD → Temporal）。"""
    client = await Client.connect(address or TEMPORAL_ADDRESS)
    return await client.execute_workflow(
        RunTaskWorkflow.run,
        inp,
        id=workflow_id,
        task_queue=TASK_QUEUE,
        execution_timeout=timedelta(minutes=20),
    )
