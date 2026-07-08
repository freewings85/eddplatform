"""评估维度扩展：轨迹结构（最小链路）+ TTFT + 成本；EvalContext 扩字段。"""

from eddplatform.domain.models import EvaluatorDef, EvaluatorKind, OutputType
from eddplatform.evals.engine import (
    EvalContext,
    MaxCost,
    MaxTTFT,
    MinimalToolChain,
    build_evaluator,
)


def _ctx(**kw) -> EvalContext:
    return EvalContext(inputs=None, output=None, **kw)


# --- EvalContext 新字段 ----------------------------------------------------
def test_eval_context_carries_signal_fields():
    ctx = _ctx(ttft_s=0.4, usage={"input": 90, "output": 40}, cost=0.011)
    assert ctx.ttft_s == 0.4
    assert ctx.usage["output"] == 40
    assert ctx.cost == 0.011


def test_eval_context_signal_fields_default_empty():
    ctx = _ctx()
    assert ctx.ttft_s is None
    assert ctx.usage == {}
    assert ctx.cost is None


# --- 轨迹质量：最小调用链路 ------------------------------------------------
def test_minimal_tool_chain_passes_within_limit_and_unique():
    spans = [{"name": "tool:quote", "kind": "tool"}, {"name": "tool:store", "kind": "tool"}]
    assert MinimalToolChain(name="最小链路", max_calls=2).evaluate(_ctx(spans=spans)).passed


def test_minimal_tool_chain_fails_on_too_many_calls():
    spans = [{"name": f"tool:{i}", "kind": "tool"} for i in range(3)]
    assert not MinimalToolChain(name="最小链路", max_calls=2).evaluate(_ctx(spans=spans)).passed


def test_minimal_tool_chain_fails_on_duplicate_call():
    spans = [{"name": "tool:quote", "kind": "tool"}, {"name": "tool:quote", "kind": "tool"}]
    assert not MinimalToolChain(name="最小链路", max_calls=5,
                                no_duplicate=True).evaluate(_ctx(spans=spans)).passed


def test_minimal_tool_chain_ignores_non_tool_spans():
    spans = [{"name": "tool:quote", "kind": "tool"}, {"name": "llm.explain", "kind": "generation"}]
    assert MinimalToolChain(name="最小链路", max_calls=1).evaluate(_ctx(spans=spans)).passed


# --- 信号类门禁：TTFT / 成本 ----------------------------------------------
def test_max_ttft_gate():
    assert MaxTTFT(name="ttft", seconds=0.8).evaluate(_ctx(ttft_s=0.5)).passed
    assert not MaxTTFT(name="ttft", seconds=0.8).evaluate(_ctx(ttft_s=1.2)).passed


def test_max_ttft_fails_when_not_measured():
    assert not MaxTTFT(name="ttft", seconds=0.8).evaluate(_ctx(ttft_s=None)).passed


def test_max_cost_gate():
    assert MaxCost(name="cost", budget=0.02).evaluate(_ctx(cost=0.01)).passed
    assert not MaxCost(name="cost", budget=0.02).evaluate(_ctx(cost=0.05)).passed


# --- EvaluatorDef → 新评估器装配 ------------------------------------------
def test_build_evaluator_maps_new_dimensions():
    for bt, cls, attr, val in [("MaxTTFT", MaxTTFT, "seconds", 0.8),
                               ("MaxCost", MaxCost, "budget", 0.02)]:
        d = EvaluatorDef(name=bt, kind=EvaluatorKind.BUILTIN, builtin_type=bt,
                         threshold=val, output_type=OutputType.ASSERTION)
        ev = build_evaluator(d)
        assert isinstance(ev, cls)
        assert getattr(ev, attr) == val


def test_build_evaluator_minimal_tool_chain():
    d = EvaluatorDef(name="最小链路", kind=EvaluatorKind.BUILTIN, builtin_type="MinimalToolChain",
                     threshold=2, output_type=OutputType.ASSERTION)
    ev = build_evaluator(d)
    assert isinstance(ev, MinimalToolChain)
    assert ev.max_calls == 2


# --- Langfuse 适配器：信号类指标 → Boolean 门禁 Score（离线可测的纯工厂）---
def test_signal_gate_turns_metric_into_boolean_score():
    from eddplatform.evals.adapters.langfuse import signal_gate

    gate = signal_gate("TTFT达标", key="ttft_s", threshold=0.8, mode="max")
    ok = gate(input=None, output={"ttft_s": 0.5}, expected_output=None, metadata=None)
    bad = gate(input=None, output={"ttft_s": 1.2}, expected_output=None, metadata=None)
    assert ok["value"] is True and bad["value"] is False
    assert ok["data_type"] == "BOOLEAN"


def test_signal_gate_reads_from_metadata_and_min_mode():
    from eddplatform.evals.adapters.langfuse import signal_gate

    # 成本从 metadata 取；mode=max 表示"越小越好"，≤ 阈值达标
    gate = signal_gate("成本达标", key="cost", threshold=0.02, mode="max")
    out = gate(input=None, output={}, expected_output=None, metadata={"cost": 0.03})
    assert out["value"] is False
