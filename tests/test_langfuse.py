"""Langfuse 集成：从 trace 里聚合「真实、完整」的每会话生成 token。

纯聚合逻辑（sum_generation_usage）与轮询装配（session_usage，注入 fetcher/sleep，
不打网络）分开测；HTTP 薄壳由实跑验证，不在单测覆盖。
"""
from eddplatform.integrations import langfuse


def _gen(inp, out, total=None, cached=0, cache_key="input_cached_tokens", typ="GENERATION"):
    o = {"type": typ, "usage": {"input": inp, "output": out}}
    if total is not None:
        o["usage"]["total"] = total
    if cached:
        o["usageDetails"] = {cache_key: cached}
    return o


def test_sums_only_generation_observations():
    obs = [_gen(100, 10), _gen(200, 20),
           {"type": "AGENT", "usage": {"input": 999, "output": 99}},   # 父聚合，排除防重复
           {"type": "SPAN", "usage": {"input": 5, "output": 5}}]
    agg = langfuse.sum_generation_usage(obs)
    assert agg["input"] == 300 and agg["output"] == 30
    assert agg["generations"] == 2


def test_total_falls_back_to_input_plus_output():
    assert langfuse.sum_generation_usage([_gen(100, 10)])["total"] == 110


def test_total_uses_reported_when_present():
    assert langfuse.sum_generation_usage([_gen(100, 10, total=150)])["total"] == 150


def test_cache_read_from_both_key_variants_and_fresh():
    obs = [_gen(100, 10, cached=40, cache_key="input_cached_tokens"),
           _gen(100, 10, cached=30, cache_key="cache_read_input_tokens")]
    agg = langfuse.sum_generation_usage(obs)
    assert agg["cache_read"] == 70
    assert agg["fresh_input"] == 200 - 70


def test_empty_is_all_zero():
    assert langfuse.sum_generation_usage([]) == {
        "input": 0, "output": 0, "total": 0, "cache_read": 0,
        "generations": 0, "fresh_input": 0}


def test_session_usage_returns_once_generations_appear():
    """异步摄取：先空后就绪 —— 命中即返回，不再多轮。"""
    calls = {"n": 0}

    def fetcher(_sid):
        calls["n"] += 1
        if calls["n"] < 2:
            return [], 0                       # 尚未摄取
        return [_gen(1732, 30, cached=1024)], 1
    slept = []
    agg = langfuse.session_usage("s1", fetcher=fetcher, attempts=5,
                                 interval=9, sleep=slept.append)
    assert agg["generations"] == 1 and agg["traces"] == 1
    assert agg["cache_read"] == 1024 and agg["fresh_input"] == 1732 - 1024
    assert calls["n"] == 2 and slept == [9]     # 只等了一次


def test_session_usage_times_out_gracefully():
    """一直没摄取到：优雅返回零值（不抛异常，不阻断评估）。"""
    def fetcher(_sid):
        return [], 0
    slept = []
    agg = langfuse.session_usage("s1", fetcher=fetcher, attempts=3,
                                 interval=2, sleep=slept.append)
    assert agg["generations"] == 0 and agg["traces"] == 0
    assert slept == [2, 2]                       # attempts-1 次等待


def test_session_usage_survives_fetcher_errors():
    """Langfuse 抖动/网络错误：吞掉，当作未就绪继续，最终优雅返回。"""
    def fetcher(_sid):
        raise ConnectionError("langfuse down")
    agg = langfuse.session_usage("s1", fetcher=fetcher, attempts=2,
                                 interval=0, sleep=lambda _s: None)
    assert agg["generations"] == 0


def test_to_token_usage_maps_to_evaluator_keys():
    """session_usage 的结果映射成评估器读的 *_tokens 约定键。"""
    lf = {"input": 13489, "output": 208, "total": 13747, "cache_read": 9216,
          "fresh_input": 4273, "generations": 4, "traces": 1}
    u = langfuse.to_token_usage(lf)
    assert u["input_tokens"] == 13489
    assert u["output_tokens"] == 208
    assert u["total_tokens"] == 13747
    assert u["cache_read_tokens"] == 9216
    assert u["cache_write_tokens"] == 0
    assert u["generations"] == 4


def test_to_token_usage_defaults_missing_to_zero():
    assert langfuse.to_token_usage({}) == {
        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0, "generations": 0}
