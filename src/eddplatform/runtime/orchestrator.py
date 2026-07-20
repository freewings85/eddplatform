"""前置条件编排：按顺序把 task 的前置条件立起来，产出一个**版本可感知**的环境。

一次运行（= experiment 的执行）：给定一组有序 ``Precondition`` 和一个一次性 namespace，
依次执行——``start_system`` / ``start_eval_program`` 走约定式部署器（ConventionDeployer），
``custom_script`` 跑脚本——同一个 namespace 里多个 helm release 共存。

产出 ``EnvironmentResult``：每条前置条件的结果 + **结构化版本标签** ``{system: sha,
eval: sha}``。这就是把"系统代码 × 评估代码 两个版本化主体"在一个环境里交叉起来、
且平台明确知道用了哪些版本——老新对比 / 复现的地基。
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Sequence

from eddplatform.domain.models import Precondition, PreconditionKind
from eddplatform.runtime.deployer import ConventionDeployer

# 前置条件类型 → 结构化版本标签里的角色名
_ROLE = {
    PreconditionKind.START_SYSTEM: "system",
    PreconditionKind.START_EVAL_PROGRAM: "eval",
}


@dataclass
class PreconditionOutcome:
    kind: str
    name: str
    status: str                        # ok | failed
    ref: str | None = None             # 解析出的 git sha（版本可感知）
    images: dict[str, str] = field(default_factory=dict)
    detail: str = ""


@dataclass
class EnvironmentResult:
    namespace: str
    status: str                        # up | failed
    versions: dict[str, str] = field(default_factory=dict)   # {system: sha, eval: sha}
    outcomes: list[PreconditionOutcome] = field(default_factory=list)
    releases: list[str] = field(default_factory=list)        # 已装的 helm release（供销毁）


class Orchestrator:
    def __init__(
        self,
        deployer: ConventionDeployer | None = None,
        *,
        kubeconfig: str | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self._log = log or (lambda m: print(m))
        self.deployer = deployer or ConventionDeployer(kubeconfig=kubeconfig, log=self._log)
        self.kubeconfig = kubeconfig or self.deployer.kubeconfig

    # --- 对外 ------------------------------------------------------------
    def bring_up(self, preconditions: Sequence[Precondition], namespace: str) -> EnvironmentResult:
        """按顺序执行前置条件；任一失败即停并标记 failed（已起的仍记录，便于销毁）。"""
        env = EnvironmentResult(namespace=namespace, status="up")
        for i, pc in enumerate(preconditions):
            name = pc.name or f"{pc.kind.value}-{i}"
            self._log(f"— 前置条件 [{i + 1}/{len(preconditions)}] {pc.kind.value} «{name}»")
            try:
                self._run_one(pc, name, namespace, env)
            except Exception as e:  # noqa: BLE001 —— 记录并中止，不让异常逃逸
                env.status = "failed"
                env.outcomes.append(
                    PreconditionOutcome(pc.kind.value, name, "failed", detail=str(e))
                )
                self._log(f"✗ 前置条件失败，中止: {e}")
                break
        return env

    def tear_down(self, env: EnvironmentResult) -> None:
        for release in env.releases:
            self.deployer.uninstall(release=release, namespace=env.namespace)
        self.deployer.delete_namespace(env.namespace)
        self._log(f"✓ 已销毁环境 ns/{env.namespace}")

    # --- 内部 ------------------------------------------------------------
    def _run_one(
        self, pc: Precondition, name: str, namespace: str, env: EnvironmentResult
    ) -> None:
        if pc.kind in (PreconditionKind.START_SYSTEM, PreconditionKind.START_EVAL_PROGRAM):
            ref = pc.commit or pc.branch
            if not pc.git_url or not ref:
                raise ValueError(f"{pc.kind.value} 需要 git_url 和 ref（运行时选定的版本）")
            res = self.deployer.deploy(
                git_url=pc.git_url, ref=ref, release=name, namespace=namespace, path=pc.path or "."
            )
            env.releases.append(name)
            env.versions[name] = res.ref
            env.outcomes.append(
                PreconditionOutcome(pc.kind.value, name, "ok", ref=res.ref, images=res.images)
            )
        elif pc.kind == PreconditionKind.CUSTOM_SCRIPT:
            if not pc.script:
                raise ValueError("custom_script 需要 script 内容")
            self._run_script(pc.script, namespace)
            env.outcomes.append(PreconditionOutcome(pc.kind.value, name, "ok"))
        else:  # pragma: no cover
            raise ValueError(f"未知前置条件类型: {pc.kind}")

    def _run_script(self, script: str, namespace: str) -> None:
        environ = {**os.environ, "KUBECONFIG": self.kubeconfig, "EDD_NAMESPACE": namespace}
        proc = subprocess.run(
            ["bash", "-c", script], env=environ, check=False, capture_output=True, text=True
        )
        if proc.returncode != 0:
            raise RuntimeError(f"脚本失败({proc.returncode}): {proc.stderr or proc.stdout}")
