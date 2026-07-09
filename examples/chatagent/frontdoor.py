"""EDD **前门入口适配器**：驱动真实多进程系统的"完整一轮"——经前门 orchestrator
``POST /chat/stream``（异步编排 + Kafka→SSE 桥），把 SSE 事件流聚合成与
``make_chatagent_target`` 同形的 ``{output, tool_calls, usage, latency_s, error}``，
让评估器无改动复用。这是"前门到前门"公平对比两套完整系统所需的入口。

为什么走前门：直接打某个下游进程的 /chat/run 只测到"某个点"（如 2.0 的 collect
agent 只到参数抽取，绕过了 workflows+BMA 编排）。前门驱动才把两套系统的**完整链路**
（2.0: orchestrator→workflows→BMA→chatagent2→toolprovider；2.3: orchestrator→
chatagent3→toolexecutor）都测进去，时延/成本/文案才可比。

SSE 帧：``event: <type>\\ndata: <event-json>\\n\\n``（见 orchestrator server/chat.py
_stream_from_kafka）。事件 JSON 形状（见 chatagent3 events/model.py EventModel）::

    {"session_id","request_id","type","data",...}

- type=text          → data.content（拼成最终回复）
- type=tool_call_start→ data.{tool_name,tool_call_id}
- type=tool_call_args → data.{tool_call_id,args_chunk}（分片，按 id 拼成完整 args JSON）
- type=usage         → data.usage（token；2.0 若摊平则退回 data 本身）
- type=chat_request_end（request_id==root）→ 该轮结束
"""

from __future__ import annotations

import itertools
import json
import subprocess
import time
from typing import Any, Callable

_SESSION = itertools.count(1)


# ── 纯解析核心（可单测，不碰 k8s）─────────────────────────────────────────────
def iter_sse_events(raw: str) -> list[dict]:
    """把 SSE 文本拆成事件 dict 列表（只取每个 ``data:`` 行的 JSON，忽略注释/空行）。"""
    events: list[dict] = []
    for line in raw.splitlines():
        if not line.startswith("data:"):
            continue  # `event:` 行、注释(`:`)、空行都跳过——type 从 data JSON 里读
        payload = line[len("data:"):].strip()
        if not payload:
            continue
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    return events


_USAGE_KEYS = ("input_tokens", "output_tokens", "total_tokens",
               "cache_read_tokens", "cache_write_tokens")


def sum_usage(usages: list[dict]) -> dict:
    """把多轮的 per-turn usage 逐 key 相加（缺失键当 0）。空列表 → {}。

    多轮对比要看"整段会话"的 token 账，尤其 ``cache_read_tokens`` 会随轮次上升——
    单轮汇总看不出缓存命中，多轮相加才能拆出 非缓存(fresh)=input-cache_read。
    """
    if not usages:
        return {}
    return {k: sum(int(u.get(k, 0) or 0) for u in usages) for k in _USAGE_KEYS}


def _belongs(event: dict, root_id: str) -> bool:
    """事件属于本轮：request_id == root，或 root 的子树(root|...)。别的请求忽略。"""
    rid = event.get("request_id", "")
    return rid == root_id or rid.startswith(f"{root_id}|")


def aggregate_events(events: list[dict], *, root_id: str) -> dict:
    """把本轮(含子树)事件聚合成 {output, tool_calls, usage}。"""
    text_parts: list[str] = []
    tool_order: list[str] = []
    tool_name: dict[str, str] = {}
    tool_args_chunks: dict[str, list[str]] = {}
    usage: dict = {}

    for ev in events:
        if not _belongs(ev, root_id):
            continue
        etype = ev.get("type")
        data = ev.get("data") or {}
        if etype == "text":
            text_parts.append(str(data.get("content") or ""))
        elif etype == "tool_call_start":
            tcid = data.get("tool_call_id") or ""
            if tcid not in tool_name:
                tool_order.append(tcid)
            tool_name[tcid] = data.get("tool_name") or "unknown"
            tool_args_chunks.setdefault(tcid, [])
        elif etype == "tool_call_args":
            tcid = data.get("tool_call_id") or ""
            if tcid not in tool_args_chunks:
                tool_order.append(tcid)
                tool_args_chunks[tcid] = []
            tool_args_chunks[tcid].append(str(data.get("args_chunk") or ""))
        elif etype == "usage":
            # 2.3 嵌套在 data.usage；2.0 若摊平则退回 data 本身。
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else data

    tool_calls: list[dict] = []
    for tcid in tool_order:
        raw_args = "".join(tool_args_chunks.get(tcid, []))
        if raw_args:
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {"_raw": raw_args}
        else:
            args = {}
        tool_calls.append({"tool_name": tool_name.get(tcid, "unknown"), "args": args})

    return {"output": "".join(text_parts), "tool_calls": tool_calls, "usage": usage}


# ── k8s I/O 薄壳：exec 进前门 pod curl /chat/stream，读 SSE ────────────────────
def _stream_chat(namespace: str, orch: str, port: int, body: dict, timeout: int) -> str:
    proc = subprocess.run(
        ["kubectl", "exec", "-i", "-n", namespace, f"deploy/{orch}", "--",
         "curl", "-sN", "-m", str(timeout - 5), "-X", "POST",
         f"localhost:{port}/chat/stream",
         "-H", "Content-Type: application/json", "-d", "@-"],
        input=json.dumps(body), text=True, capture_output=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"/chat/stream exec 失败: {proc.stderr[:300]}")
    return proc.stdout


def _choose_usage(usage_sse: dict, usage_true: dict | None) -> tuple[dict, str]:
    """真实(Langfuse 全链路)用量有 token 就用它，否则退回 SSE。返回 (usage, source)。

    2.0 分布式下 BMA 分类/路由、collect 子 agent 的 token 都在下游进程里，前门 SSE
    看不到、会严重少算；Langfuse 按 session 把整轮所有 GENERATION 相加才是真实完整值。
    """
    if usage_true and usage_true.get("total_tokens"):
        return usage_true, "langfuse"
    return usage_sse, "sse"


def make_frontdoor_target(
    namespace: str, orch: str = "orchestrator", port: int = 7100,
    user_id: str = "edd", turn_timeout: int = 180,
    usage_lookup: Callable[[str, int], dict | None] | None = None,
) -> Callable[[Any], dict]:
    """构造"前门到前门"的 target：经 orchestrator /chat/stream 驱动完整一轮。

    每轮生成唯一 request_id 作 root；SSE 到该 root 的 chat_request_end 即该轮结束。
    多轮共用 session_id。返回聚合 {output, tool_calls, usage, latency_s, error}。

    ``usage_lookup(session_id, n_turns) -> {*_tokens}|None``：注入的真实用量来源
    （Langfuse 全链路 token）。给了且有值就覆盖 SSE 少算的用量；None/返回空则退回 SSE。
    依赖注入让本模块不硬依赖 eddplatform —— 由调用方（systems/chatagent）接上 Langfuse。
    """

    def target(inputs: Any) -> dict:
        turns = inputs.get("turns") or [{"user": inputs.get("message", "")}]
        session_id = f"edd-{next(_SESSION)}-{int(time.time())}"
        all_tool_calls: list[dict] = []
        per_turn_usage: list[dict] = []
        output = ""
        error = None
        t0 = time.perf_counter()
        for i, turn in enumerate(turns):
            request_id = f"{session_id}-r{i}"
            body = {"session_id": session_id, "user_id": user_id,
                    "message": turn["user"], "request_id": request_id}
            try:
                raw = _stream_chat(namespace, orch, port, body, turn_timeout)
            except Exception as e:  # noqa: BLE001
                error = str(e)[:200]
                continue
            events = iter_sse_events(raw)
            agg = aggregate_events(events, root_id=request_id)
            if agg["output"]:
                output = agg["output"]           # 末轮回复即最终回复
            all_tool_calls.extend(agg["tool_calls"])
            if agg["usage"]:
                per_turn_usage.append(agg["usage"])   # 逐轮攒，最后相加（多轮缓存分账）
            if not events:
                error = error or f"空 SSE（{raw[:120]!r}）"
        latency_s = time.perf_counter() - t0     # 先定格时延——不含下面 Langfuse 轮询

        usage_sse = sum_usage(per_turn_usage)
        usage_true = None
        if usage_lookup is not None:
            try:                                  # best-effort：Langfuse 抖动不阻断评估
                usage_true = usage_lookup(session_id, len(turns))
            except Exception:  # noqa: BLE001
                usage_true = None
        usage, usage_source = _choose_usage(usage_sse, usage_true)
        return {"output": output, "tool_calls": all_tool_calls,
                "usage": usage, "usage_source": usage_source,
                "usage_sse": usage_sse, "usage_true": usage_true,
                "usage_per_turn": per_turn_usage,
                "latency_s": latency_s, "error": error}

    return target
