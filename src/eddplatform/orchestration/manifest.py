"""Harbor：把「系统版本」渲染成部署 manifest（每个服务钉住 image:tag）。

纯函数，无外部依赖。真实 Harbor 集成（校验 tag 存在、拉 digest）见
``integrations/harbor.py``（薄壳，可选）。
"""

from __future__ import annotations

from eddplatform.domain.models import Module, SystemVersion


def render_manifest(modules: list[Module], version: SystemVersion) -> dict:
    """由 ``version.module_pins`` + 模块元数据渲染部署 manifest。

    每个服务钉住 ``<module.image>:<pinned tag>``；未在 modules 里登记的服务退化用
    服务名当镜像名（脚手架容错）。
    """
    by_name = {m.name: m for m in modules}
    services = []
    for name, tag in version.module_pins.items():
        m = by_name.get(name)
        image = m.image if m else name
        services.append({
            "name": name,
            "image": f"{image}:{tag}",
            "healthcheck": m.healthcheck if m else "/healthz",
        })
    return {"system_id": version.system_id, "version": version.label, "services": services}
