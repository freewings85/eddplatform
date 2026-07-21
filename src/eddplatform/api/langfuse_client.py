"""Langfuse 公共 API 薄客户端：连接测试 + 拉取 trace（归档）+ 回灌 trace（恢复）。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

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


def trace_id_from_url(url: str) -> str:
    """Langfuse 轨迹链接 → trace id（``…/traces/<id>`` 或旧式 ``…/trace/<id>``）。"""
    from urllib.parse import urlparse
    parts = [p for p in urlparse(url.strip()).path.split("/") if p]
    for marker in ("traces", "trace"):
        if marker in parts:
            i = parts.index(marker)
            if i + 1 < len(parts) and parts[i + 1]:
                return parts[i + 1]
    raise LangfuseError(
        f"链接里找不到 trace id（应形如 …/traces/<id>）: {url.strip()!r}")


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


_TRACE_KEYS = ("id", "timestamp", "name", "userId", "input", "output", "sessionId",
               "metadata", "tags", "release", "version", "public")
_OBS_KEYS = ("id", "traceId", "type", "name", "startTime", "endTime",
             "completionStartTime", "model", "modelParameters", "input", "output",
             "metadata", "parentObservationId", "level", "statusMessage", "version", "usage")
_SCORE_KEYS = ("id", "traceId", "name", "value", "observationId", "comment")


def events_from_archive(data: dict) -> list[dict]:
    """归档的 trace JSON → ingestion 事件批（恢复回 Langfuse 用，保留原 id）。"""
    now = datetime.now(timezone.utc).isoformat()

    def ev(etype: str, body: dict) -> dict:
        return {"id": str(uuid.uuid4()), "type": etype, "timestamp": now,
                "body": {k: v for k, v in body.items() if v is not None}}

    events = [ev("trace-create", {k: data.get(k) for k in _TRACE_KEYS})]
    for o in data.get("observations") or []:
        body = {k: o.get(k) for k in _OBS_KEYS}
        if body.get("traceId") is None:
            body["traceId"] = data.get("id")
        events.append(ev("observation-create", body))
    for sc in data.get("scores") or []:
        body = {k: sc.get(k) for k in _SCORE_KEYS}
        if body.get("traceId") is None:
            body["traceId"] = data.get("id")
        events.append(ev("score-create", body))
    return events


def restore_trace(settings: GlobalSettings, data: dict) -> dict:
    """把归档的完整 trace 回灌进 Langfuse（同 id 幂等 upsert），返回可打开的 URL。"""
    auth = _auth(settings)
    host = settings.langfuse_host.rstrip("/")
    trace_id = data.get("id")
    if not trace_id:
        raise LangfuseError("归档数据缺少 trace id，无法恢复")
    events = events_from_archive(data)
    try:
        r = httpx.post(f"{host}/api/public/ingestion", json={"batch": events},
                       auth=auth, timeout=60)
    except httpx.HTTPError as e:
        raise LangfuseError(f"连不上 Langfuse: {e}")
    if r.status_code not in (200, 207):
        raise LangfuseError(f"Langfuse 返回 {r.status_code}: {r.text[:200]}")
    errors = (r.json() or {}).get("errors") or []
    if errors:
        raise LangfuseError(f"部分事件回灌失败: {errors[0]}")
    # 拼可打开的 URL（需要 project id）
    pr = httpx.get(f"{host}/api/public/projects", auth=auth, timeout=10)
    pid = (pr.json().get("data") or [{}])[0].get("id", "")
    url = f"{host}/project/{pid}/traces/{trace_id}" if pid else f"{host}/traces/{trace_id}"
    return {"trace_id": trace_id, "url": url, "events": len(events)}
