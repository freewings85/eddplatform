"""Backstage 薄壳：把系统/模块登记到软件目录（可选）。

平台复用 Backstage catalog 做统一门户/SSO；这里只做最薄的登记调用。需配置
``BACKSTAGE_URL`` / ``BACKSTAGE_TOKEN``；未配置时报错（本机通常无 Backstage 实例）。
"""

from __future__ import annotations

import os

_ENV = ("BACKSTAGE_URL", "BACKSTAGE_TOKEN")


def available() -> bool:
    return all(os.environ.get(k) for k in _ENV)


def register_component(component: dict) -> dict:
    """向 Backstage catalog 登记一个 Component（对应平台的 Module）。"""
    if not available():
        raise RuntimeError(
            "登记到 Backstage 需要配置 BACKSTAGE_URL / BACKSTAGE_TOKEN；"
            "本机通常无 Backstage 实例，可跳过（平台其余流程不依赖它）。"
        )
    import httpx

    base = os.environ["BACKSTAGE_URL"].rstrip("/")
    resp = httpx.post(
        f"{base}/api/catalog/locations",
        headers={"Authorization": f"Bearer {os.environ['BACKSTAGE_TOKEN']}"},
        json={"type": "url", "target": component.get("catalog_url", "")},
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json()
