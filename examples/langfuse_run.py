"""端到端：用 Langfuse 当引擎，把「保险报价系统」v1 vs v2 跑出老新对比。

前置：本地 Langfuse 已起（deploy/langfuse/ 里 `docker compose up -d`），并设置：
    export LANGFUSE_HOST=http://localhost:3100
    export LANGFUSE_PUBLIC_KEY=pk-lf-eddplatform-local
    export LANGFUSE_SECRET_KEY=sk-lf-eddplatform-local

运行：
    python examples/langfuse_run.py

做的事：① 把用例集 sync 成 Langfuse dataset；② v1、v2 各跑一次 dataset run
（run_experiment 自动追踪 + 打分）；③ 打印在 Langfuse Compare 看对比的入口。
被评"系统"这里用普通函数模拟——真实项目换成打沙箱入口的 HttpTarget 即可。
"""

import os

from eddplatform.domain.models import Case, Dataset
from eddplatform.evals.adapters import langfuse as lf

# --- 用例集（对 v1/v2 都适用）---------------------------------------------
DATASET = Dataset(
    name="保险报价",
    system_id="insurance",
    cases=[
        Case(id="17", name="新能源车型报价", inputs={"car": "ev"},
             expected_output={"premium": 4260}),
        Case(id="88", name="含优惠叠加报价", inputs={"car": "petrol", "promo": True},
             expected_output={"premium": 3100}),
        Case(id="91", name="历史出险影响保费", inputs={"car": "ev", "claims": 2},
             expected_output={"premium": 5200}),
    ],
)


# --- 被评系统（黑盒；真实项目 = HttpTarget 打沙箱入口）---------------------
def system_v1(inputs):
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 3820}          # v1 bug on #17
    return {"premium": 5200 if inputs.get("claims") else 3100}


def system_v2(inputs):
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 4260}          # v2 fixed
    return {"premium": 5200 if inputs.get("claims") else 3100}


# --- 评估器（v4 evaluator 函数：返回 {name, value, comment}）---------------
def amount_check(*, input, output, expected_output, metadata=None, **kwargs):
    got = output.get("premium") if isinstance(output, dict) else None
    exp = expected_output.get("premium") if isinstance(expected_output, dict) else None
    return {"name": "金额校验", "value": got == exp, "comment": f"{got} vs 期望 {exp}"}


EVALUATORS = [amount_check]


def main():
    host = os.environ.get("LANGFUSE_HOST", "http://localhost:3100")
    print(f"Langfuse: {host}")
    lf.sync_dataset(DATASET)
    print(f"✓ 已 sync dataset「{DATASET.name}」({len(DATASET.cases)} 用例)")

    r1 = lf.run_version(DATASET.name, "insurance-v1", system_v1, EVALUATORS)
    print(f"✓ v1 run 完成: insurance-v1  (通过率 {_pass_rate(r1)})")
    r2 = lf.run_version(DATASET.name, "insurance-v2", system_v2, EVALUATORS)
    print(f"✓ v2 run 完成: insurance-v2  (通过率 {_pass_rate(r2)})")

    print("\n对比 →", lf.compare_hint(host, DATASET.name, "insurance-v1", "insurance-v2"))


def _pass_rate(result) -> str:
    """尽力从 ExperimentResult 里数一下通过率（SDK 版本不同字段略异）。"""
    items = getattr(result, "item_results", None) or getattr(result, "items", None) or []
    passed = total = 0
    for it in items:
        evals = getattr(it, "evaluations", None) or []
        for e in evals:
            v = e.get("value") if isinstance(e, dict) else getattr(e, "value", None)
            total += 1
            if v is True or v == 1:
                passed += 1
    return f"{passed}/{total}" if total else "?"


if __name__ == "__main__":
    main()
