"""前门 SSE 适配器的纯解析核心测试（TDD）。

orchestrator /chat/stream 回一串 SSE：`event: <type>\\ndata: <event-json>\\n\\n`。
适配器要把它聚合成与 make_chatagent_target 同形的 {output, tool_calls, usage}，
让评估器无改动复用。这里只测纯函数（喂字节流、断言聚合），不碰 k8s。
"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, ".")

from examples.chatagent.frontdoor import (  # noqa: E402
    _choose_usage,
    aggregate_events,
    iter_sse_events,
    sum_usage,
)


def test_choose_usage_prefers_true_when_it_has_tokens():
    """Langfuse 真实用量（全链路 token）有值就用它——SSE 会严重少算 2.0 分布式 token。"""
    sse = {"input_tokens": 1200, "total_tokens": 1300, "cache_read_tokens": 0}
    true = {"input_tokens": 13489, "total_tokens": 13747, "cache_read_tokens": 9216}
    usage, source = _choose_usage(sse, true)
    assert usage is true and source == "langfuse"


def test_choose_usage_falls_back_to_sse_when_true_absent_or_empty():
    sse = {"input_tokens": 1200, "total_tokens": 1300}
    for true in (None, {}, {"total_tokens": 0}):
        usage, source = _choose_usage(sse, true)
        assert usage is sse and source == "sse"


def _sse(*events: dict) -> str:
    import json
    blocks = []
    for e in events:
        blocks.append(f"event: {e['type']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n")
    return "".join(blocks)


ROOT = "req-1"


def _ev(type_, data, request_id=ROOT):
    return {"session_id": "s1", "request_id": request_id, "type": type_, "data": data}


def test_iter_sse_events_parses_data_lines_to_dicts():
    raw = _sse(_ev("text", {"content": "你好"}), _ev("chat_request_end", {}))
    events = iter_sse_events(raw)
    assert [e["type"] for e in events] == ["text", "chat_request_end"]
    assert events[0]["data"]["content"] == "你好"


def test_iter_sse_events_tolerates_blank_and_comment_lines():
    raw = ": keepalive\n\n" + _sse(_ev("text", {"content": "hi"}))
    events = iter_sse_events(raw)
    assert [e["type"] for e in events] == ["text"]


def test_aggregate_concatenates_text_into_output():
    events = [
        _ev("chat_request_start", {}),
        _ev("text", {"content": "你好"}),
        _ev("text", {"content": "，在的"}),
        _ev("text", {"content": ""}),  # 收尾空 text（带 finish_reason），不该丢字
        _ev("chat_request_end", {}),
    ]
    out = aggregate_events(events, root_id=ROOT)
    assert out["output"] == "你好，在的"


def test_aggregate_assembles_streamed_tool_call_args():
    events = [
        _ev("tool_call_start", {"tool_name": "search_shops", "tool_call_id": "t1"}),
        _ev("tool_call_args", {"tool_call_id": "t1", "args_chunk": '{"location"'}),
        _ev("tool_call_args", {"tool_call_id": "t1", "args_chunk": ':"北京","asks_price":true}'}),
        _ev("chat_request_end", {}),
    ]
    out = aggregate_events(events, root_id=ROOT)
    assert out["tool_calls"] == [
        {"tool_name": "search_shops", "args": {"location": "北京", "asks_price": True}}
    ]


def test_aggregate_reads_nested_usage_payload():
    events = [
        _ev("usage", {"user_id": "u", "usage": {"total_tokens": 1234, "cache_read_tokens": 1000}}),
        _ev("chat_request_end", {}),
    ]
    out = aggregate_events(events, root_id=ROOT)
    assert out["usage"]["total_tokens"] == 1234
    assert out["usage"]["cache_read_tokens"] == 1000


def test_aggregate_usage_falls_back_to_flat_data():
    """2.0 workflows 若把 usage 直接摊平在 data 里（非 data.usage 嵌套），也要能读。"""
    events = [_ev("usage", {"total_tokens": 42}), _ev("chat_request_end", {})]
    out = aggregate_events(events, root_id=ROOT)
    assert out["usage"]["total_tokens"] == 42


def test_aggregate_ignores_events_from_other_request_subtrees_for_output():
    """只聚合 root 或其子树(root|...)的事件；别的请求串进来（不同 request_id）要忽略。"""
    events = [
        _ev("text", {"content": "属于本轮"}, request_id=ROOT),
        _ev("text", {"content": "别的请求"}, request_id="req-OTHER"),
        _ev("text", {"content": "子树也算"}, request_id=f"{ROOT}|child"),
        _ev("chat_request_end", {}),
    ]
    out = aggregate_events(events, root_id=ROOT)
    assert out["output"] == "属于本轮子树也算"


def test_aggregate_malformed_tool_args_kept_as_raw():
    events = [
        _ev("tool_call_start", {"tool_name": "x", "tool_call_id": "t1"}),
        _ev("tool_call_args", {"tool_call_id": "t1", "args_chunk": "not-json"}),
        _ev("chat_request_end", {}),
    ]
    out = aggregate_events(events, root_id=ROOT)
    assert out["tool_calls"][0]["args"] == {"_raw": "not-json"}


# ── 多轮 usage 汇总（缓存/非缓存分账所需）────────────────────────────────────
def test_sum_usage_empty_is_empty():
    assert sum_usage([]) == {}


def test_sum_usage_single_passthrough():
    u = {"input_tokens": 10, "cache_read_tokens": 0, "output_tokens": 5, "total_tokens": 15}
    assert sum_usage([u]) == {"input_tokens": 10, "cache_read_tokens": 0,
                              "output_tokens": 5, "total_tokens": 15, "cache_write_tokens": 0}


def test_sum_usage_adds_across_turns_incl_missing_keys():
    """多轮：逐 key 相加；缺失键当 0（如冷启轮无 cache_read）。"""
    turns = [
        {"input_tokens": 12907, "cache_read_tokens": 0, "output_tokens": 52, "total_tokens": 12959},
        {"input_tokens": 52803, "cache_read_tokens": 49408, "output_tokens": 310, "total_tokens": 53113},
    ]
    s = sum_usage(turns)
    assert s["input_tokens"] == 65710
    assert s["cache_read_tokens"] == 49408
    assert s["output_tokens"] == 362
    assert s["total_tokens"] == 66072
    # 派生：非缓存(fresh) input = input - cache_read = 16302
    assert s["input_tokens"] - s["cache_read_tokens"] == 16302
