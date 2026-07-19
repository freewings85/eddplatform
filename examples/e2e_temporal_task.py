"""端到端：EDD 启动一个 task = 把参数传给 Temporal → 拉起 workflow 跑（真集群 + 真 Temporal）。

链路（需 k3s + helm + buildah + git + Temporal server + 一个 worker）：
  1. 用 examples/demo-system、demo-eval 各造一个真实 git 仓库；
  2. 起一个 Temporal worker（子进程，托管 RunTaskWorkflow + 活动）；
  3. EDD 侧 client 把 task 参数（有序前置条件 + 版本 ref + 评估观测目标）提交给 Temporal；
  4. workflow 依次跑活动：启动系统 → 启动评估程序 → seed 脚本 → 评估程序观测系统；
  5. 断言运行记录：环境 up、结构化版本标签、评估观测到系统内容；
  6. 销毁 k8s 环境、停 worker。

前置：`temporal server start-dev` 已在跑（localhost:7233）。运行：
    python examples/e2e_temporal_task.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from eddplatform.domain.models import Precondition, PreconditionKind
from eddplatform.runtime import ConventionDeployer
from eddplatform.runtime.temporal import RunTaskInput, to_spec
from eddplatform.runtime.temporal.client import run_task

EXAMPLES = Path(__file__).resolve().parent
NS = "edd-temporal"


def sh(*cmd: str, cwd: Path | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def make_repo(src: Path, dst: Path) -> str:
    shutil.copytree(src, dst)
    sh("git", "init", "-q", cwd=dst)
    sh("git", "config", "user.email", "e2e@edd.local", cwd=dst)
    sh("git", "config", "user.name", "edd-e2e", cwd=dst)
    sh("git", "add", "-A", cwd=dst)
    sh("git", "commit", "-qm", src.name, cwd=dst)
    return sh("git", "rev-parse", "HEAD", cwd=dst)


def start_worker(log_path: Path) -> subprocess.Popen:
    env = {**os.environ, "KUBECONFIG": "/etc/rancher/k3s/k3s.yaml",
           "PATH": "/usr/local/bin:" + os.environ.get("PATH", "")}
    proc = subprocess.Popen(
        [sys.executable, "-m", "eddplatform.runtime.temporal.worker"],
        env=env, stdout=log_path.open("w"), stderr=subprocess.STDOUT,
    )
    for _ in range(30):  # 等 worker 连上
        if log_path.exists() and "等待任务" in log_path.read_text():
            break
        time.sleep(0.5)
    return proc


async def submit(shas: dict[str, str], urls: dict[str, str]):
    preconditions = [
        Precondition(kind=PreconditionKind.START_SYSTEM, name="system",
                     git_url=urls["system"], ref=shas["system"]),
        Precondition(kind=PreconditionKind.START_EVAL_PROGRAM, name="eval",
                     git_url=urls["eval"], ref=shas["eval"]),
        Precondition(kind=PreconditionKind.CUSTOM_SCRIPT, name="seed",
                     script='kubectl -n "$EDD_NAMESPACE" create configmap seed --from-literal=ok=1'),
    ]
    inp = RunTaskInput(
        preconditions=[to_spec(p) for p in preconditions],
        namespace=NS, eval_deploy="judge", eval_target="quote",
    )
    return await run_task(inp, workflow_id=f"edd-task-{int(time.time())}")


def main() -> int:
    worker = None
    ok = False
    out = None
    try:
        with TemporaryDirectory(prefix="edd-temporal-") as tmp:
            tmp_p = Path(tmp)
            log = tmp_p / "worker.log"
            urls = {"system": f"file://{tmp_p / 'sys'}", "eval": f"file://{tmp_p / 'eval'}"}
            shas = {"system": make_repo(EXAMPLES / "demo-system", tmp_p / "sys"),
                    "eval": make_repo(EXAMPLES / "demo-eval", tmp_p / "eval")}
            print(f"system git @ {shas['system'][:12]}, eval git @ {shas['eval'][:12]}")

            print("启动 Temporal worker…")
            worker = start_worker(log)

            print("EDD → Temporal 提交 task…")
            out = asyncio.run(submit(shas, urls))

            print("\n===== 运行记录（workflow 返回）=====")
            print(f"namespace={out.namespace} status={out.status}")
            print(f"versions={out.versions}")
            for o in out.outcomes:
                print(f"  - {o.kind} «{o.name}» {o.status} ref={o.ref}")
            print(f"评估观测 result={out.result}")

            print("\n===== 断言 =====")
            checks = {
                "status up": out.status == "up",
                "versions 有 system+eval": {"system", "eval"} <= set(out.versions),
                "评估观测到系统内容": "demo-system" in out.result.get("observed", ""),
            }
            for k, v in checks.items():
                print(f"  [{'✓' if v else '✗'}] {k}")
            ok = all(checks.values())
    finally:
        if out is not None:
            print("\n===== 销毁 =====")
            dep = ConventionDeployer()
            for rel in out.releases:
                dep.uninstall(release=rel, namespace=out.namespace)
            dep.delete_namespace(out.namespace)
        if worker is not None:
            worker.terminate()
            worker.wait(timeout=10)

    print("\n" + ("✅ Temporal 端到端通过" if ok else "❌ Temporal 端到端失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
