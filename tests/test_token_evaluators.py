"""token 分账评估器测试（TDD）：把 usage 拆成 input / 缓存命中 / 非缓存(fresh) / 命中率，
让多轮对比能看清"token 里的 cache 和非 cache"。"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, ".")

from eddplatform.evals.engine import EvalContext  # noqa: E402
from examples.chatagent.evaluators import (  # noqa: E402
    CacheHitRate,
    CacheReadTokens,
    FreshTokens,
    InputTokens,
)


def _ctx(usage):
    return EvalContext(inputs={}, output={"usage": usage})


def test_input_tokens_reads_input():
    assert InputTokens().evaluate(_ctx({"input_tokens": 1000})).value == 1000


def test_cache_read_tokens_reads_cache_read():
    assert CacheReadTokens().evaluate(_ctx({"cache_read_tokens": 800})).value == 800


def test_fresh_tokens_is_input_minus_cache_read():
    v = FreshTokens().evaluate(_ctx({"input_tokens": 1000, "cache_read_tokens": 800})).value
    assert v == 200


def test_fresh_tokens_no_cache_equals_input():
    v = FreshTokens().evaluate(_ctx({"input_tokens": 1000, "cache_read_tokens": 0})).value
    assert v == 1000


def test_cache_hit_rate():
    v = CacheHitRate().evaluate(_ctx({"input_tokens": 1000, "cache_read_tokens": 800})).value
    assert abs(v - 0.8) < 1e-9


def test_cache_hit_rate_zero_input_is_zero():
    v = CacheHitRate().evaluate(_ctx({"input_tokens": 0, "cache_read_tokens": 0})).value
    assert v == 0.0
