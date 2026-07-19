"""端到端验证：前置条件编排——系统代码 × 评估代码 两个版本化主体，一起拉起到同一环境。

真实链路（需 k3s + helm + buildah + git）：
  1. 用 examples/demo-system、examples/demo-eval 各造一个**真实 git 仓库**；
  2. 组一个 task 的有序前置条件：start_system → start_eval_program → custom_script(seed)；
  3. Orchestrator 依次执行，把被测系统(quote+gateway) + 评估程序(judge)拉进同一个一次性
     namespace，并跑 seed 脚本；
  4. 断言：环境 up、三个服务 pod 都 Running、结构化版本标签 {system: sha, eval: sha}、
     seed 的 configmap 存在；
  5. 销毁。

    python examples/e2e_task_orchestration.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from eddplatform.domain.models import Precondition, PreconditionKind
from eddplatform.runtime import Orchestrator

EXAMPLES = Path(__file__).resolve().parent


def sh(*cmd: str, cwd: Path | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def make_repo(src: Path, dst: Path) -> str:
    """把示例目录拷成一个真实单提交 git 仓库，返回 (file:// url, sha)。"""
    shutil.copytree(src, dst)
    sh("git", "init", "-q", cwd=dst)
    sh("git", "config", "user.email", "e2e@edd.local", cwd=dst)
    sh("git", "config", "user.name", "edd-e2e", cwd=dst)
    sh("git", "add", "-A", cwd=dst)
    sh("git", "commit", "-qm", f"{src.name}", cwd=dst)
    return sh("git", "rev-parse", "HEAD", cwd=dst)


def pod_phase(namespace: str, deploy: str) -> str:
    return sh("kubectl", "-n", namespace, "get", "pods", "-l", f"app={deploy}",
              "-o", "jsonpath={.items[0].status.phase}")


def main() -> int:
    ns = "edd-task"
    with tempfile.TemporaryDirectory(prefix="edd-task-") as tmp:
        tmp_p = Path(tmp)
        sys_url = f"file://{tmp_p / 'sys'}"
        eval_url = f"file://{tmp_p / 'eval'}"
        sys_sha = make_repo(EXAMPLES / "demo-system", tmp_p / "sys")
        eval_sha = make_repo(EXAMPLES / "demo-eval", tmp_p / "eval")
        print(f"被测系统 git: {sys_url} @ {sys_sha[:12]}")
        print(f"评估程序 git: {eval_url} @ {eval_sha[:12]}\n")

        # 一个 task 的有序前置条件（版本此刻才选定 = 运行时选版本）
        preconditions = [
            Precondition(kind=PreconditionKind.START_SYSTEM, name="system",
                         git_url=sys_url, ref=sys_sha),
            Precondition(kind=PreconditionKind.START_EVAL_PROGRAM, name="eval",
                         git_url=eval_url, ref=eval_sha),
            Precondition(kind=PreconditionKind.CUSTOM_SCRIPT, name="seed",
                         script='kubectl -n "$EDD_NAMESPACE" create configmap seed '
                                '--from-literal=ok=1'),
        ]

        orch = Orchestrator()
        env = orch.bring_up(preconditions, ns)

        ok = env.status == "up"
        print("\n===== 断言 =====")
        checks = {
            "quote Running": pod_phase(ns, "quote") == "Running",
            "gateway Running": pod_phase(ns, "gateway") == "Running",
            "judge Running": pod_phase(ns, "judge") == "Running",
            "versions 有 system+eval": {"system", "eval"} <= set(env.versions),
            "seed configmap 存在":
                sh("kubectl", "-n", ns, "get", "configmap", "seed", "-o", "name") == "configmap/seed",
        }
        for k, v in checks.items():
            print(f"  [{'✓' if v else '✗'}] {k}")
            ok = ok and v

        print("\n===== 结构化环境（版本可感知）=====")
        print(f"namespace: {env.namespace}  status: {env.status}")
        print(f"versions: {env.versions}")
        for o in env.outcomes:
            print(f"  - {o.kind} «{o.name}» {o.status} ref={o.ref} images={o.images}")

        print("\n===== 销毁 =====")
        orch.tear_down(env)

    print("\n" + ("✅ 端到端通过" if ok else "❌ 端到端失败"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
