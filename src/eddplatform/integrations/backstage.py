"""Backstage 薄壳：把系统/模块登记到软件目录（可选）。

平台复用 Backstage catalog 做统一门户/SSO；这里只做最薄的登记调用。需配置
``BACKSTAGE_URL`` / ``BACKSTAGE_TOKEN``；未配置时报错（本机通常无 Backstage 实例）。
"""

from __future__ import annotations

import os

import httpx

from eddplatform.domain.models import Module, System

_ENV = ("BACKSTAGE_URL", "BACKSTAGE_TOKEN")


def available() -> bool:
    return all(os.environ.get(k) for k in _ENV)


def _http() -> httpx.Client:
    """Backstage HTTP 客户端（Bearer + 超时）。测试可 monkeypatch 换 MockTransport。"""
    return httpx.Client(
        headers={"Authorization": f"Bearer {os.environ['BACKSTAGE_TOKEN']}"}, timeout=15.0)


def component_descriptor(module: Module) -> dict:
    """由平台 Module 生成 Backstage Component 实体（可写进 catalog-info.yaml）。纯函数。"""
    return {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "Component",
        "metadata": {
            "name": module.name,
            "annotations": {"backstage.io/source-location": f"url:{module.git_url}"},
        },
        "spec": {"type": "service", "lifecycle": "production",
                 "owner": module.owner or "unknown"},
    }


def system_descriptor(system: System) -> dict:
    """由平台 System 生成 Backstage System 实体。纯函数。"""
    return {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "System",
        "metadata": {"name": system.id},
        "spec": {"owner": system.owner or "unknown"},
    }


def register_location(catalog_url: str) -> dict:
    """向 Backstage 注册一个指向 catalog-info 的 location（Backstage 真实摄入方式）。"""
    if not available():
        raise RuntimeError(
            "登记到 Backstage 需要配置 BACKSTAGE_URL / BACKSTAGE_TOKEN；"
            "本机通常无 Backstage 实例，可跳过（平台其余流程不依赖它）。")
    base = os.environ["BACKSTAGE_URL"].rstrip("/")
    with _http() as client:
        resp = client.post(f"{base}/api/catalog/locations",
                           json={"type": "url", "target": catalog_url},
                           headers={"Authorization": f"Bearer {os.environ['BACKSTAGE_TOKEN']}"})
    resp.raise_for_status()
    return resp.json()


def register_component(component: dict) -> dict:
    """向 Backstage catalog 登记一个 Component（对应平台 Module）。

    Backstage 按 location 摄入：传入 ``component["catalog_url"]`` 指向该 Component 的
    catalog-info.yaml。未配置时报可操作错误。
    """
    return register_location(component.get("catalog_url", ""))
