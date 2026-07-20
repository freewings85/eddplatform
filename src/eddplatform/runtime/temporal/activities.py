"""Temporal 活动：把真正干活的部分（会做 I/O 的）包成活动。

活动是**同步**函数（会 shell out git/buildah/helm/kubectl），worker 用线程池执行。
"""

from __future__ import annotations

import os
import subprocess

from temporalio import activity

from eddplatform.runtime.deployer import ConventionDeployer
from eddplatform.runtime.temporal.shared import (DeployArgs, DeployOut, EvalArgs,
                                                 ScriptArgs, WaitWorkerArgs)


class TaskActivities:
    """一组活动，共享一个部署器（可注入，便于替换 image sink / 测试）。"""

    def __init__(self, deployer: ConventionDeployer | None = None) -> None:
        self.deployer = deployer or ConventionDeployer(log=activity_logger)

    @activity.defn
    def deploy_repo(self, args: DeployArgs) -> DeployOut:
        """拉起一份具体版本的 git 代码（系统或评估程序）到 namespace。"""
        res = self.deployer.deploy(
            git_url=args.git_url, ref=args.ref, release=args.release,
            namespace=args.namespace, path=args.path,
        )
        return DeployOut(
            role=args.role, release=res.release, ref=res.ref, images=res.images, pods=res.pods
        )

    @activity.defn
    def run_script(self, args: ScriptArgs) -> None:
        env = {**os.environ, "KUBECONFIG": self.deployer.kubeconfig, "EDD_NAMESPACE": args.namespace}
        proc = subprocess.run(
            ["bash", "-c", args.script], env=env, check=False, capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise RuntimeError(f"脚本失败({proc.returncode}): {proc.stderr or proc.stdout}")

    @activity.defn
    def wait_eval_worker(self, args: WaitWorkerArgs) -> None:
        """队列预检：等评估程序 worker 认领队列；宽限期内没等到 → 明确报错 fail fast。

        没有这步时，workflow 名配错/worker 没起来会让每条用例干等到超时。
        """
        import asyncio
        import time

        from temporalio.api.enums.v1 import TaskQueueType
        from temporalio.api.taskqueue.v1 import TaskQueue
        from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest
        from temporalio.client import Client

        address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")

        async def has_poller() -> bool:
            client = await Client.connect(address)
            resp = await client.workflow_service.describe_task_queue(
                DescribeTaskQueueRequest(
                    namespace=client.namespace,
                    task_queue=TaskQueue(name=args.queue),
                    task_queue_type=TaskQueueType.TASK_QUEUE_TYPE_WORKFLOW,
                ))
            return len(resp.pollers) > 0

        deadline = time.time() + args.timeout_s
        while time.time() < deadline:
            if asyncio.run(has_poller()):
                return
            activity_logger(f"等待评估 worker 认领队列 {args.queue!r}…")
            time.sleep(3)
        raise RuntimeError(
            f"评估 workflow {args.queue!r} 没有 worker 认领队列——评估程序没起来，"
            "或用例库配置的 workflow 名与评估程序代码里注册的不一致")

    @activity.defn
    def run_eval(self, args: EvalArgs) -> dict:
        """评估观测：让评估程序（如 judge）去观测被测系统（如 quote），记录观测结果。

        这是「评估程序真正跑起来对系统做评估」最小但真实的一步——由 Temporal 活动驱动。
        """
        env = {**os.environ, "KUBECONFIG": self.deployer.kubeconfig}
        observed = subprocess.run(
            ["kubectl", "-n", args.namespace, "exec", f"deploy/{args.eval_deploy}",
             "--", "wget", "-qO-", f"http://{args.target}"],
            env=env, check=True, capture_output=True, text=True,
        ).stdout.strip()
        return {"eval_deploy": args.eval_deploy, "target": args.target, "observed": observed}


def activity_logger(msg: str) -> None:
    try:
        activity.logger.info(msg)
    except Exception:  # noqa: BLE001 —— 活动上下文外调用时退化为 print
        print(msg)
