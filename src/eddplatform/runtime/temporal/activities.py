"""Temporal 活动：把真正干活的部分（会做 I/O 的）包成活动。

活动是**同步**函数（会 shell out git/buildah/helm/kubectl），worker 用线程池执行。
每个活动带 ``run_id`` 时，执行日志（clone/构建/helm 等每一步）落库到 ``run_logs``，
界面「运行记录 → 控制台输出」实时可见（Jenkins 控制台输出的等价物）。
"""

from __future__ import annotations

import os
import subprocess
import time

from temporalio import activity

from eddplatform.runtime.deployer import ConventionDeployer
from eddplatform.runtime.temporal.shared import (DeployArgs, DeployOut, DestroyArgs,
                                                 EvalArgs, LogArgs, ScriptArgs,
                                                 WaitWorkerArgs)


class _RunLogWriter:
    """把日志行缓冲写进 run_logs 表；DB 不可用时静默降级（日志绝不拖垮执行）。"""

    FLUSH_LINES = 25
    FLUSH_SECS = 1.5

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._buf: list[str] = []
        self._last = time.time()
        self._store = None
        self._dead = False

    def __call__(self, msg: str) -> None:
        activity_logger(msg)
        if not self.run_id or self._dead:
            return
        self._buf.extend(msg.splitlines() or [""])
        if len(self._buf) >= self.FLUSH_LINES or time.time() - self._last > self.FLUSH_SECS:
            self.flush()

    def flush(self) -> None:
        if not self._buf or self._dead:
            return
        try:
            if self._store is None:
                from eddplatform.store.run_log_store import RunLogStore
                self._store = RunLogStore()
            self._store.append(self.run_id, "\n".join(self._buf))
            self._buf = []
            self._last = time.time()
        except Exception as e:  # noqa: BLE001 —— 落库失败只降级，不影响部署/评估
            activity_logger(f"(run_logs 落库失败，控制台日志降级为仅 worker stdout: {e})")
            self._dead = True


class TaskActivities:
    """一组活动，共享一个部署器（可注入，便于替换 image sink / 测试）。"""

    def __init__(self, deployer: ConventionDeployer | None = None) -> None:
        self.deployer = deployer or ConventionDeployer(log=activity_logger)

    @activity.defn
    def deploy_repo(self, args: DeployArgs) -> DeployOut:
        """拉起一份具体版本的 git 代码（系统或评估程序）到 namespace。"""
        log = _RunLogWriter(args.run_id)
        deployer = self.deployer
        with_log = getattr(deployer, "with_log", None)
        if callable(with_log):
            deployer = with_log(log)
        try:
            res = deployer.deploy(
                git_url=args.git_url, ref=args.ref, release=args.release,
                namespace=args.namespace, path=args.path, env=args.env,
            )
        except Exception as e:
            log(f"✗ 部署失败: {e}")
            raise
        finally:
            log.flush()
        return DeployOut(
            role=args.role, release=res.release, ref=res.ref, images=res.images, pods=res.pods
        )

    @activity.defn
    def run_script(self, args: ScriptArgs) -> None:
        log = _RunLogWriter(args.run_id)
        log(f"$ {args.script}")
        env = {**os.environ, "KUBECONFIG": self.deployer.kubeconfig, "EDD_NAMESPACE": args.namespace}
        proc = subprocess.run(
            ["bash", "-c", args.script], env=env, check=False, capture_output=True, text=True
        )
        for out in (proc.stdout, proc.stderr):
            if out and out.strip():
                log(out.rstrip("\n"))
        log.flush()
        if proc.returncode != 0:
            raise RuntimeError(f"脚本失败({proc.returncode}): {proc.stderr or proc.stdout}")

    @activity.defn
    def destroy_namespace(self, args: DestroyArgs) -> None:
        """任务选了「运行后销毁资源」：删掉本次运行的一次性 namespace（异步删除）。"""
        log = _RunLogWriter(args.run_id)
        log(f"$ kubectl delete ns {args.namespace} --wait=false")
        self.deployer.delete_namespace(args.namespace)
        log(f"✓ 已发起销毁 namespace {args.namespace}（k8s 后台完成清理）")
        log.flush()

    @activity.defn
    def append_run_log(self, args: LogArgs) -> None:
        """workflow 侧的编排级日志（逐用例分派进度等）——单独一个轻活动落库。"""
        w = _RunLogWriter(args.run_id)
        w(args.line)
        w.flush()

    @activity.defn
    def wait_eval_worker(self, args: WaitWorkerArgs) -> None:
        """队列预检：等评估程序 worker 认领队列；宽限期内没等到 → 明确报错 fail fast。

        没有这步时，workflow 名配错/worker 没起来会让每条用例干等到超时。
        """
        import asyncio

        from temporalio.api.enums.v1 import TaskQueueType
        from temporalio.api.taskqueue.v1 import TaskQueue
        from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest
        from temporalio.client import Client

        log = _RunLogWriter(args.run_id)
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

        try:
            deadline = time.time() + args.timeout_s
            while time.time() < deadline:
                if asyncio.run(has_poller()):
                    log(f"✓ 评估 worker 已认领队列 {args.queue!r}")
                    return
                log(f"等待评估 worker 认领队列 {args.queue!r}…")
                time.sleep(3)
            raise RuntimeError(
                f"评估 workflow {args.queue!r} 没有 worker 认领队列——评估程序没起来，"
                "或用例库配置的 workflow 名与评估程序代码里注册的不一致")
        finally:
            log.flush()

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
