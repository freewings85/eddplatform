"""Temporal worker：托管 RunTaskWorkflow + 活动。

    python -m eddplatform.runtime.temporal.worker      # 需要 Temporal server 在跑

活动是同步阻塞（git/buildah/helm/kubectl），用线程池执行。
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from eddplatform.runtime.temporal.activities import TaskActivities
from eddplatform.runtime.temporal.shared import TASK_QUEUE
from eddplatform.runtime.temporal.workflows import RunTaskWorkflow

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS)
    acts = TaskActivities()
    with ThreadPoolExecutor(max_workers=8) as executor:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=[RunTaskWorkflow],
            activities=[acts.deploy_repo, acts.run_script, acts.run_eval,
                        acts.wait_eval_worker, acts.append_run_log],
            activity_executor=executor,
        )
        print(f"worker 已连接 {TEMPORAL_ADDRESS}，task_queue={TASK_QUEUE}，等待任务…")
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
