"""评估内核测试：中立接口 + 本地兜底评分器，全程离线、零框架依赖。"""

import sys

from eddplatform.domain.models import Case, EvaluatorDef, EvaluatorKind, OutputType
from eddplatform.evals.engine import (
    EqualsExpected,
    MaxDuration,
    build_evaluator,
    compare,
    run,
)

CASES = [
    Case(id="17", name="新能源车型报价", inputs={"car": "ev"},
         expected_output={"premium": 4260}, evaluator_names=["金额校验", "延迟阈值"]),
    Case(id="88", name="含优惠叠加报价", inputs={"car": "petrol"},
         expected_output={"premium": 3100}, evaluator_names=["金额校验", "延迟阈值"]),
    Case(id="91", name="历史出险影响保费", inputs={"car": "ev", "claims": 2},
         expected_output={"premium": 5200}, evaluator_names=["金额校验", "延迟阈值"]),
]
EVALUATORS = {
    "金额校验": EqualsExpected(name="金额校验", path="$.premium"),
    "延迟阈值": MaxDuration(name="延迟阈值", seconds=5.0),
}


def _v1(inputs):
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 3820}          # bug on #17
    return {"premium": 5200 if inputs.get("claims") else 3100}


def _v2(inputs):
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 4260}          # fixed
    return {"premium": 5200 if inputs.get("claims") else 3100}


def test_local_engine_runs_offline():
    assert run(_v2, CASES, EVALUATORS).pass_rate == 1.0
    assert run(_v1, CASES, EVALUATORS).pass_rate < 1.0


def test_compare_detects_improvement():
    c = compare(run(_v1, CASES, EVALUATORS), run(_v2, CASES, EVALUATORS))
    assert c.improved == 1
    assert c.regressed == 0
    assert c.applicable_cases == 3


def test_engine_has_no_agent_framework_dependency():
    """中立引擎绝不拉 pydantic-ai / pydantic-evals / langgraph。"""
    assert "pydantic_evals" not in sys.modules
    assert "pydantic_ai" not in sys.modules
    assert "langgraph" not in sys.modules


def test_build_evaluator_from_def():
    d = EvaluatorDef(name="延迟", kind=EvaluatorKind.BUILTIN, builtin_type="MaxDuration",
                     threshold=3.0, output_type=OutputType.ASSERTION)
    ev = build_evaluator(d)
    assert isinstance(ev, MaxDuration)
    assert ev.seconds == 3.0


def test_langfuse_adapter_is_optional():
    """未装 langfuse 时适配器可 import，且 available() 如实反映。"""
    from eddplatform.evals.adapters import langfuse as lf_adapter

    assert isinstance(lf_adapter.available(), bool)
