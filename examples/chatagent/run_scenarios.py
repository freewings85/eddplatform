"""EDD 用例驱动跑三场景(guide/searchshops/searchcoupons)评估一个部署的方案。

    PYTHONPATH=src python examples/chatagent/run_scenarios.py [namespace] [scenario]

scenario 可选 all|guide|searchshops|searchcoupons（默认 all）。打印逐用例结果 + 分场景通过率。
返回的 EvalResult 也可交给 compare() 做老新对比。
"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, ".")
from eddplatform.evals.engine import run  # noqa: E402
from examples.chatagent.cases import (  # noqa: E402
    GUIDE_CASES,
    SEARCHCOUPONS_CASES,
    SEARCHSHOPS_CASES,
)
from examples.chatagent.evaluators import all_evaluators  # noqa: E402
from examples.chatagent.target import make_chatagent_target  # noqa: E402

NS = sys.argv[1] if len(sys.argv) > 1 else "edd-2-3"
SCEN = sys.argv[2] if len(sys.argv) > 2 else "all"
DIMS = ["维度-成本token", "维度-时延s"]
GROUPS = {"guide": GUIDE_CASES, "searchshops": SEARCHSHOPS_CASES, "searchcoupons": SEARCHCOUPONS_CASES}
picked = GROUPS if SCEN == "all" else {SCEN: GROUPS[SCEN]}

target = make_chatagent_target(NS)
evs = all_evaluators()

for scen, group in picked.items():
    cases = [c.model_copy(update={"evaluator_names": c.evaluator_names + DIMS}) for c in group]
    result = run(target, cases, evs)
    print(f"\n===== {scen}  pass_rate={result.pass_rate:.0%}  ({NS}) =====")
    for cr in result.case_results:
        mark = "✅" if cr.passed else "❌"
        fails = [k for k, v in cr.assertions.items() if not v]
        cost = cr.scores.get("维度-成本token", 0)
        lat = cr.scores.get("维度-时延s", 0)
        print(f"{mark} {cr.case_id:32} tok={cost:>7.0f} lat={lat:>5.1f}s"
              + (f"   失败:{fails}" if fails else ""))
