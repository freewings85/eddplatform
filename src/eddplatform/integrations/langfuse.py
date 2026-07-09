"""Langfuse 集成 —— 从 trace 里读**真实、完整**的每会话生成 token。

为什么需要它：前门 SSE 只汇报编排器看得见的一小部分用量（2.0 分布式下 BMA 分类/路由、
collect 子 agent 的 token 都在下游进程里，前门看不到，会被严重少算）。真实链路里每一次
LLM 调用都被 pydantic-ai 原生埋点成一个 GENERATION span，经 OTel collector 打到 Langfuse，
整轮（编排 + BMA + collect + 生成）归到同一个 ``session.id`` 下。按会话把这些 GENERATION 的
用量相加，才得到「完整、含 cache 命中拆分」的真实 token。

设计：纯聚合（``sum_generation_usage``，可单测）与轮询装配（``session_usage``，注入
fetcher/sleep）分离；HTTP 薄壳（``_http_fetch_session``）best-effort，Langfuse 不可达时
静默返回零值，绝不阻断评估。默认连本机自建 Langfuse（compose 映射 :3100）。
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.parse
import urllib.request
from typing import Callable

# 本机自建 Langfuse 默认值（deploy/langfuse/.env 里初始化的 project key）。
_DEFAULT_HOST = "http://127.0.0.1:3100"
_DEFAULT_PUBLIC = "pk-lf-eddplatform-local"
_DEFAULT_SECRET = "sk-lf-eddplatform-local"

_ZERO = {"input": 0, "output": 0, "total": 0, "cache_read": 0, "generations": 0}


def _cfg() -> tuple[str, str, str]:
    return (
        os.environ.get("LANGFUSE_HOST", _DEFAULT_HOST).rstrip("/"),
        os.environ.get("LANGFUSE_PUBLIC_KEY", _DEFAULT_PUBLIC),
        os.environ.get("LANGFUSE_SECRET_KEY", _DEFAULT_SECRET),
    )


def _auth(pk: str, sk: str) -> str:
    return "Basic " + base64.b64encode(f"{pk}:{sk}".encode()).decode()


# ── 纯聚合：把一批 observation 里的 GENERATION 用量相加 ──────────────────────
def sum_generation_usage(observations: list[dict]) -> dict:
    """只累加 ``type == "GENERATION"`` 的 span —— AGENT/父级是聚合，累加会重复计数。

    ``total`` 缺省用 input+output 兜底；``cache_read`` 兼容 Langfuse 两种键名
    （usageDetails.input_cached_tokens / cache_read_input_tokens）。
    """
    agg = dict(_ZERO)
    for o in observations:
        if o.get("type") != "GENERATION":
            continue
        u = o.get("usage") or {}
        ud = o.get("usageDetails") or {}
        inp = u.get("input") or 0
        out = u.get("output") or 0
        agg["input"] += inp
        agg["output"] += out
        agg["total"] += u.get("total") or (inp + out)
        agg["cache_read"] += (
            ud.get("input_cached_tokens") or ud.get("cache_read_input_tokens") or 0
        )
        agg["generations"] += 1
    agg["fresh_input"] = agg["input"] - agg["cache_read"]
    return agg


# ── HTTP 薄壳：按 session 拉全部 trace 的 observation ────────────────────────
def _get(host: str, auth: str, path: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(host + path, headers={"Authorization": auth})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (本机自建)
        return json.load(r)


def _http_fetch_session(session_id: str) -> tuple[list[dict], int]:
    """返回（该会话所有 trace 的 observation 列表, trace 数）。"""
    host, pk, sk = _cfg()
    auth = _auth(pk, sk)
    q = urllib.parse.urlencode({"sessionId": session_id, "limit": 100})
    traces = _get(host, auth, f"/api/public/traces?{q}").get("data", [])
    obs: list[dict] = []
    for tr in traces:
        detail = _get(host, auth, f"/api/public/traces/{tr['id']}")
        obs.extend(detail.get("observations", []))
    return obs, len(traces)


# ── 轮询装配：等异步摄取就绪，聚合并返回 ───────────────────────────────────
def session_usage(
    session_id: str,
    *,
    expected_traces: int = 1,
    attempts: int = 8,
    interval: float = 3.0,
    fetcher: Callable[[str], tuple[list[dict], int]] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """按 ``session_id`` 拉真实、完整的生成用量（含 cache/fresh 拆分）。

    Langfuse 摄取是异步的（collector 批量 2s + 服务端处理数秒），故轮询：一旦拉到
    ``>= expected_traces`` 个 trace 且有 GENERATION 就返回；否则最多 ``attempts`` 次、
    每次隔 ``interval`` 秒。fetcher/网络异常一律吞掉（当作未就绪），超时返回最后一次
    聚合（通常是零值）——best-effort，绝不让 Langfuse 抖动阻断一次评估。
    """
    fetch = fetcher or _http_fetch_session
    agg = dict(_ZERO, fresh_input=0, traces=0)
    for i in range(attempts):
        try:
            obs, ntraces = fetch(session_id)
        except Exception:  # noqa: BLE001  网络/服务抖动 → 视作未就绪
            obs, ntraces = [], 0
        agg = sum_generation_usage(obs)
        agg["traces"] = ntraces
        if ntraces >= expected_traces and agg["generations"] > 0:
            return agg
        if i < attempts - 1:
            sleep(interval)
    return agg


def to_token_usage(lf: dict) -> dict:
    """把 ``session_usage`` 的结果映射成评估器读的 ``*_tokens`` 约定键。

    评估器（CostTokens/InputTokens/CacheReadTokens/FreshTokens/CacheHitRate）统一读
    ``input_tokens/output_tokens/total_tokens/cache_read_tokens``；映射后即可无改动复用。
    这些模型无「cache write」计费，故 ``cache_write_tokens`` 恒 0。
    """
    return {
        "input_tokens": lf.get("input", 0),
        "output_tokens": lf.get("output", 0),
        "total_tokens": lf.get("total", 0),
        "cache_read_tokens": lf.get("cache_read", 0),
        "cache_write_tokens": 0,
        "generations": lf.get("generations", 0),
    }


def available(timeout: float = 3.0) -> bool:
    """Langfuse 是否可达且 key 有效（拉一次 projects 列表看是否 2xx）。"""
    host, pk, sk = _cfg()
    try:
        _get(host, _auth(pk, sk), "/api/public/projects", timeout=timeout)
        return True
    except Exception:  # noqa: BLE001
        return False
