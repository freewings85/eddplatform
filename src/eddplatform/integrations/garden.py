"""Garden/k8s 一次性环境 provider（薄壳）。

实现 orchestration.providers.EnvironmentProvider 接口。真实底座需要 ``garden`` +
``kubectl`` + 一个 k8s 集群。**本机无集群**：``available()`` 返回 False，``create``
明确报错并指向 MockProvider——不假装成功（见项目记忆 local-env-infra-constraints）。
真集群时把下面的 shell-out 补全即可，接口对 pipeline 透明。
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from eddplatform.domain.models import RunStatus


def available() -> bool:
    """需要 garden + kubectl 在 PATH（真集群还需 kubeconfig 指向可用集群）。"""
    return shutil.which("garden") is not None and shutil.which("kubectl") is not None


@dataclass
class GardenProvider:
    """按 manifest 在 k8s namespace 拉起隔离环境；跑完销毁。"""

    namespace_prefix: str = "edd"

    def _require(self) -> None:
        if not available():
            raise RuntimeError(
                "GardenProvider 需要 garden + kubectl + 可用 k8s 集群；"
                "本机无集群，离线/CI 请用 orchestration.providers.MockProvider。"
            )

    def create(self, manifest: dict, ttl_hours: float = 2.0) -> str:
        self._require()
        ns = f"{self.namespace_prefix}-{manifest.get('version', 'env')}"
        subprocess.run(["kubectl", "create", "namespace", ns], check=True)
        # 真实实现：把 manifest 渲染成 Garden project / k8s 资源后 `garden deploy`。
        return ns

    def status(self, env_id: str) -> RunStatus:
        self._require()
        r = subprocess.run(["kubectl", "get", "namespace", env_id],
                           capture_output=True, text=True)
        return RunStatus.RUNNING if r.returncode == 0 else RunStatus.DESTROYED

    def destroy(self, env_id: str) -> None:
        self._require()
        subprocess.run(["kubectl", "delete", "namespace", env_id, "--wait=false"], check=False)
