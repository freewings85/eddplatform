"""运行时编排：把「一份具体版本的 git 代码」按仓库约定拉起到 k8s。

薄编排：读仓库里的 ``.eddplatform.yaml`` 约定 → 拉代码 → 跑仓库自己的 build 脚本
（产出镜像）→ 把镜像送进集群 → helm 部署到一次性 namespace。这就是 task 前置条件里
``start_system`` / ``start_eval_program`` 的执行器。
"""

from eddplatform.runtime.convention import RepoSpec, read_repo_spec
from eddplatform.runtime.deployer import ConventionDeployer, DeployResult
from eddplatform.runtime.orchestrator import (
    EnvironmentResult,
    Orchestrator,
    PreconditionOutcome,
)

__all__ = [
    "RepoSpec",
    "read_repo_spec",
    "ConventionDeployer",
    "DeployResult",
    "Orchestrator",
    "EnvironmentResult",
    "PreconditionOutcome",
]
