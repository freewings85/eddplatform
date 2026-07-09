"""里程碑1：EDD 用例驱动跑 guide 五条用例，打真实部署的 chatagent3(2.3)，真实 LLM。

    PYTHONPATH=src python examples/chatagent/run_guide.py [namespace]

走 EDD 编排：run(target, cases, evaluators)。target 打 k8s 里的 /chat/run；评估器读
回复文本 + 工具轨迹 + token 判定。打印逐用例结果。
"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, ".")
from eddplatform.evals.engine import run  # noqa: E402
from examples.chatagent.cases import GUIDE_CASES  # noqa: E402
from examples.chatagent.evaluators import all_evaluators  # noqa: E402
from examples.chatagent.target import make_chatagent_target  # noqa: E402

NS = sys.argv[1] if len(sys.argv) > 1 else "edd-2-3"
DIMS = ["维度-成本token", "维度-时延s"]

cases = [c.model_copy(update={"evaluator_names": c.evaluator_names + DIMS}) for c in GUIDE_CASES]
target = make_chatagent_target(NS)
result = run(target, cases, all_evaluators())

print(f"\n===== guide 评估结果（namespace={NS}）  pass_rate={result.pass_rate:.0%} =====")
for cr in result.case_results:
    mark = "✅PASS" if cr.passed else "❌FAIL"
    print(f"\n{mark}  {cr.case_id}")
    for k, v in cr.assertions.items():
        print(f"     [{'✓' if v else '✗'}] {k}")
    for k, v in cr.scores.items():
        print(f"      · {k} = {v:.2f}" if isinstance(v, float) else f"      · {k} = {v}")
print("\nmetrics:", {k: round(v, 2) for k, v in result.metrics.items()})
