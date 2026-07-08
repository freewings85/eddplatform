"""端到端发布评估（离线）：保险报价系统 v1 vs v2，整条流水线跑通并打印结论。

    PYTHONPATH=src python examples/release_eval_demo.py

做的事：为 v1、v2 各拉一次性环境（MockProvider，无需 k8s）→ 跑同一批用例 →
本地兜底评分 → 老新对比 + 需求级达标汇总 → 环境销毁。真实底座把 MockProvider 换成
GardenProvider、target 换成打沙箱入口的 HttpTarget 即可，编排逻辑不变。
"""

from eddplatform.domain.models import Case, Dataset, Module, Requirement, SystemVersion
from eddplatform.evals.engine import EqualsExpected
from eddplatform.orchestration.pipeline import run_release_evaluation
from eddplatform.orchestration.providers import MockProvider

MODULES = [
    Module(name="quote-engine", git_url="g", image="registry/quote"),
    Module(name="dialog-agent", git_url="g", image="registry/dialog"),
]
V1 = SystemVersion(id="v1", system_id="insurance", label="v1",
                   module_pins={"quote-engine": "2.1.0", "dialog-agent": "0.9.5"})
V2 = SystemVersion(id="v2", system_id="insurance", label="v2",
                   module_pins={"quote-engine": "2.2.0", "dialog-agent": "1.0.0"},
                   requirement_ids=["R-101"])

DATASET = Dataset(name="保险报价", system_id="insurance", cases=[
    Case(id="17", name="新能源车型报价", inputs={"car": "ev"}, expected_output={"premium": 4260},
         evaluator_names=["金额校验"], requirement_ids=["R-101"]),
    Case(id="88", name="含优惠叠加报价", inputs={"car": "petrol"}, expected_output={"premium": 3100},
         evaluator_names=["金额校验"], requirement_ids=["R-101"]),
    Case(id="91", name="历史出险影响保费", inputs={"car": "ev", "claims": 2},
         expected_output={"premium": 5200}, evaluator_names=["金额校验"], requirement_ids=["R-103"]),
    Case(id="102", name="新能源专属补贴校验", inputs={"car": "ev"}, expected_output={"premium": 4260},
         applicable_versions=["v2"], evaluator_names=["金额校验"], requirement_ids=["R-101"]),
])
EVALUATORS = {"金额校验": EqualsExpected(name="金额校验", path="$.premium")}
REQUIREMENTS = [
    Requirement(id="R-101", system_id="insurance", title="新能源车型报价修复", external_key="PROJ-2043"),
    Requirement(id="R-103", system_id="insurance", title="保费计算延迟优化", external_key="PROJ-2051"),
]


def _v1(inputs):
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 3820}                       # #17 bug
    return {"premium": 5200 if inputs.get("claims") else 3100}


def _v2(inputs):
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 4260}                       # 修好 #17
    return {"premium": 5200 if inputs.get("claims") else 3100}


def make_target(label, manifest, env_id):
    print(f"  ↑ 拉起环境 {env_id}（{label}）：{[s['image'] for s in manifest['services']]}")
    return _v1 if label == "v1" else _v2


def main():
    provider = MockProvider()
    print("发布评估：保险报价系统 v1（基线） vs v2（候选）")
    res = run_release_evaluation(
        modules=MODULES, baseline_version=V1, candidate_version=V2,
        dataset=DATASET, evaluators=EVALUATORS, target_factory=make_target,
        provider=provider, requirements=REQUIREMENTS,
    )
    c = res.comparison
    print(f"\n逐用例：改善 {c.improved} · 回归 {c.regressed} · 持平 {c.unchanged} "
          f"（两版共有 {c.applicable_cases} 条）")
    print("按需求：")
    for r in c.by_requirement:
        bm = r.baseline_passed == r.total_cases
        cm = r.candidate_passed == r.total_cases
        verdict = "✅达标" if cm and not bm else "❌回归" if bm and not cm else "保持" if bm else "仍未达标"
        print(f"  {r.requirement_id} {r.title:<12} v1 {r.baseline_passed}/{r.total_cases} "
              f"→ v2 {r.candidate_passed}/{r.total_cases}  {verdict}")
    print(f"\n环境全部销毁（ephemeral）：live={provider.live_count()}")


if __name__ == "__main__":
    main()
