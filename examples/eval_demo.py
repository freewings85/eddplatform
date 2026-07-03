"""离线跑通评估内核：零 agent 框架、零 pydantic-evals、零网络。

    python examples/eval_demo.py

模拟"保险报价系统" v1(有 bug) vs v2(修好)，用同一批用例评估并对比。
真实项目里把 ``system_v1/v2`` 换成 ``HttpTarget(url=沙箱入口)`` 即可——
系统是 pydantic-ai / LangGraph / 任意服务都无所谓。
"""

from eddplatform.domain.models import Case
from eddplatform.evals.engine import EqualsExpected, MaxDuration, compare, run

CASES = [
    Case(id="17", name="新能源车型报价", inputs={"car": "ev"},
         expected_output={"premium": 4260}, evaluator_names=["金额校验", "延迟阈值"]),
    Case(id="88", name="含优惠叠加报价", inputs={"car": "petrol", "promo": True},
         expected_output={"premium": 3100}, evaluator_names=["金额校验", "延迟阈值"]),
    Case(id="91", name="历史出险影响保费", inputs={"car": "ev", "claims": 2},
         expected_output={"premium": 5200}, evaluator_names=["金额校验", "延迟阈值"]),
]

EVALUATORS = {
    "金额校验": EqualsExpected(name="金额校验", path="$.premium"),
    "延迟阈值": MaxDuration(name="延迟阈值", seconds=5.0),
}


def system_v1(inputs):
    """v1：新能源车型分类错误 → #17 金额错。"""
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 3820}
    if inputs.get("claims"):
        return {"premium": 5200}
    return {"premium": 3100}


def system_v2(inputs):
    """v2：修好了 #17。"""
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 4260}
    if inputs.get("claims"):
        return {"premium": 5200}
    return {"premium": 3100}


if __name__ == "__main__":
    r1 = run(system_v1, CASES, EVALUATORS)
    r2 = run(system_v2, CASES, EVALUATORS)
    cmp = compare(r1, r2)
    print(f"v1 通过率 {r1.pass_rate:.0%}  |  v2 通过率 {r2.pass_rate:.0%}")
    print(f"改善 {cmp.improved} · 回归 {cmp.regressed} · 持平 {cmp.unchanged}  (共 {cmp.applicable_cases} 用例)")
    for m in cmp.metrics:
        print(f"  {m.metric}: {m.baseline} → {m.candidate}  (Δ {m.delta:+.3f})")
