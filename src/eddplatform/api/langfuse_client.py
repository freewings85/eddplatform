"""Langfuse 公共 API 薄客户端：连接测试 + 拉取完整 trace（归档用）。"""

from __future__ import annotations

import httpx

from eddplatform.domain.models import GlobalSettings


class LangfuseError(Exception):
    pass


def _auth(settings: GlobalSettings) -> tuple[str, str]:
    if not (settings.langfuse_host and settings.langfuse_public_key
            and settings.langfuse_secret_key):
        raise LangfuseError("Langfuse 未配置——去「基础设置」填 Host / Public Key / Secret Key")
    return (settings.langfuse_public_key, settings.langfuse_secret_key)


def test_connection(settings: GlobalSettings) -> dict:
    auth = _auth(settings)
    try:
        r = httpx.get(f"{settings.langfuse_host.rstrip('/')}/api/public/projects",
                      auth=auth, timeout=10)
    except httpx.HTTPError as e:
        raise LangfuseError(f"连不上 Langfuse: {e}")
    if r.status_code == 401:
        raise LangfuseError("Langfuse 认证失败（Public/Secret Key 不对）")
    if r.status_code != 200:
        raise LangfuseError(f"Langfuse 返回 {r.status_code}: {r.text[:200]}")
    projects = r.json().get("data", [])
    return {"ok": True, "projects": [p.get("name") for p in projects]}


def fetch_trace(settings: GlobalSettings, trace_id: str) -> dict:
    """拉取完整 trace（含 observations/scores）——归档进用例。"""
    auth = _auth(settings)
    try:
        r = httpx.get(f"{settings.langfuse_host.rstrip('/')}/api/public/traces/{trace_id}",
                      auth=auth, timeout=30)
    except httpx.HTTPError as e:
        raise LangfuseError(f"连不上 Langfuse: {e}")
    if r.status_code == 404:
        raise LangfuseError(f"Langfuse 里找不到 trace {trace_id!r}")
    if r.status_code != 200:
        raise LangfuseError(f"Langfuse 返回 {r.status_code}: {r.text[:200]}")
    return r.json()
