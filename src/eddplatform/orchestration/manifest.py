"""Harbor：把「系统版本」渲染成部署 manifest（每个服务钉住 image:tag）。

纯函数，无外部依赖。真实 Harbor 集成（校验 tag 存在、拉 digest）见
``integrations/harbor.py``（薄壳，可选）。
"""

from __future__ import annotations

import os

from eddplatform.domain.models import BaseService, Module, SystemVersion
from eddplatform.orchestration.build import image_ref

# 所有 eddplatform 沙箱共用 host 上那一套 collector→Langfuse（不再每个沙箱起一个）。
# 沙箱 pod 经 k3d 网关名 host.k3d.internal 打到 host docker 里的共享 collector(:4318)。
# 可用 EDD_OTEL_ENDPOINT 覆盖（如换成网关 IP http://172.20.0.1:4318/v1/traces）。
DEFAULT_OTEL_ENDPOINT = os.environ.get(
    "EDD_OTEL_ENDPOINT", "http://host.k3d.internal:4318/v1/traces")


def _with_observability(name: str, module_env: dict, endpoint: str) -> dict:
    """把「指向共享 collector」的可观测性 env 注入某业务服务。

    强制 ``LOGFIRE_ENABLED=true`` + ``LOGFIRE_ENDPOINT``（保证整套沙箱都汇报到同一
    Langfuse），``OTEL_SERVICE_NAME`` 缺省用服务名、模块显式设了就保留。
    """
    env = dict(module_env)
    env["LOGFIRE_ENABLED"] = "true"
    env["LOGFIRE_ENDPOINT"] = endpoint
    env.setdefault("OTEL_SERVICE_NAME", name)
    return env


def render_manifest(
    modules: list[Module],
    version: SystemVersion,
    base_services: list[BaseService] | None = None,
    otel_endpoint: str | None = None,
) -> dict:
    """由 ``version.module_pins`` + 模块元数据渲染部署 manifest。

    每个服务钉住 ``<image>:<pinned tag>``（``module.image`` 为空时用 ``edd/<name>``
    作为本地 build 的镜像名），并带上启动信息（command/args/ports/env）供 provider
    真实拉起进程。``base_services`` 指系统依赖的基础服务（kafka/redis/pg…），一并
    渲染，部署时与业务进程放在同一 namespace。
    """
    endpoint = otel_endpoint or DEFAULT_OTEL_ENDPOINT
    by_name = {m.name: m for m in modules}
    services = []
    for name, tag in version.module_pins.items():
        m = by_name.get(name)
        # 有预构建镜像 → <image>:<tag>；否则用 build 步骤同款命名 edd/<sys>-<name>:<tag>
        image = f"{m.image}:{tag}" if (m and m.image) else image_ref(version.system_id, name, tag)
        services.append({
            "name": name,
            "image": image,
            "command": list(m.command) if m else [],
            "args": list(m.args) if m else [],
            "ports": list(m.ports) if m else [],
            # 注入共享可观测性：整套沙箱自动汇报到 host 上的 collector→Langfuse
            "env": _with_observability(name, dict(m.env) if m else {}, endpoint),
            "healthcheck": m.healthcheck if m else "/healthz",
        })
    base = [
        {"name": b.name, "image": b.image, "ports": list(b.ports), "env": dict(b.env),
         "command": list(b.command), "args": list(b.args)}
        for b in (base_services or [])
    ]
    return {
        "system_id": version.system_id,
        "version": version.label,
        "services": services,
        "base_services": base,
    }
