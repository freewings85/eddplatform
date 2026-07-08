"""一次性环境 provider：中立接口 + 离线 MockProvider。

真实底座是 Garden（在 k8s 上按 manifest 拉起隔离环境）。本机无 k8s，用 MockProvider
离线跑通编排；真集群时换 ``GardenProvider``（见 integrations/garden.py 薄壳）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from eddplatform.domain.models import RunStatus


@runtime_checkable
class EnvironmentProvider(Protocol):
    """按 manifest 拉起 / 查询 / 销毁一次性环境。"""

    def create(self, manifest: dict, ttl_hours: float = 2.0) -> str: ...
    def status(self, env_id: str) -> RunStatus: ...
    def destroy(self, env_id: str) -> None: ...


@dataclass
class MockProvider:
    """内存实现：确定性、无 k8s，供离线 / CI 跑通整条流水线。"""

    _envs: dict = field(default_factory=dict)
    _seq: int = 0

    def create(self, manifest: dict, ttl_hours: float = 2.0) -> str:
        self._seq += 1
        env_id = f"mock-env-{self._seq}"
        self._envs[env_id] = {"status": RunStatus.RUNNING, "manifest": manifest,
                              "ttl_hours": ttl_hours}
        return env_id

    def status(self, env_id: str) -> RunStatus:
        env = self._envs.get(env_id)
        return env["status"] if env else RunStatus.DESTROYED

    def destroy(self, env_id: str) -> None:
        if env_id in self._envs:
            self._envs[env_id]["status"] = RunStatus.DESTROYED

    def live_count(self) -> int:
        return sum(1 for e in self._envs.values() if e["status"] != RunStatus.DESTROYED)
