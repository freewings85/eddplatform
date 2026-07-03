"""端到端：用 Langfuse 当引擎，把「保险报价系统」v1 vs v2 跑出老新对比 + 全链路轨迹。

前置：本地 Langfuse 已起（deploy/langfuse/ 里 `docker compose up -d`），并设置：
    export LANGFUSE_HOST=http://localhost:3100
    export LANGFUSE_PUBLIC_KEY=pk-lf-eddplatform-local
    export LANGFUSE_SECRET_KEY=sk-lf-eddplatform-local

运行：
    python examples/langfuse_run.py

做的事：① 用例集 sync 成 dataset；② v1、v2 各跑一次 dataset run（run_experiment 自动
建 trace + 打分 + 建 run）；③ 被评"系统"emit 一棵 span 树（intent→quote-engine→
dialog-agent(LLM)→memory），即**全链路轨迹**；④ 打印 Langfuse Compare 入口。
真实项目里把这套 system 换成打沙箱入口的 HttpTarget（服务侧自己 emit OTel 轨迹）即可。
"""

import os

from langfuse import get_client
from langfuse.experiment import Evaluation

from eddplatform.domain.models import Case, Dataset

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


# --- 被评系统（黑盒，emit 全链路轨迹；真实项目 = 服务自身 OTel 埋点）--------
def make_system(quote_tag: str, dialog_tag: str, ev_premium: int):
    """构造一个"系统"：模拟 5 服务里的关键 3 步，各 emit 一个 span/generation。"""

    def system(inputs):
        lf = get_client()
        with lf.start_as_current_observation(
            name="intent-service.classify", as_type="tool", input=inputs
        ) as s:
            intent = "ev" if inputs.get("car") == "ev" else "petrol"
            s.update(output={"intent": intent})

        with lf.start_as_current_observation(
            name=f"quote-engine.calc:{quote_tag}", as_type="tool",
            input={"intent": intent, "claims": inputs.get("claims", 0)},
        ) as s:
            if inputs.get("claims"):
                premium = 5200
            elif intent == "ev":
                premium = ev_premium
            else:
                premium = 3100
            s.update(output={"premium": premium})

        with lf.start_as_current_observation(
            name=f"dialog-agent.explain:{dialog_tag}", as_type="generation",
            input={"premium": premium}, model="gpt-4o-mini",
        ) as s:
            text = f"您的保费为 ¥{premium}。"
            s.update(output=text, usage_details={"input": 90, "output": 40})

        with lf.start_as_current_observation(
            name="memory-service.write", as_type="span", input={"premium": premium}
        ) as s:
            s.update(output={"saved": True})

        return {"premium": premium, "explain": text}

    return system


system_v1 = make_system("2.1.0", "0.9.5", 3820)   # v1：新能源报价错(bug)
system_v2 = make_system("2.2.0", "1.0.0", 4260)   # v2：修好 #17


# --- 评估器（v4 evaluator 函数：返回 Evaluation 对象）----------------------
def amount_check(*, input, output, expected_output, metadata=None, **kwargs):
    got = output.get("premium") if isinstance(output, dict) else None
    exp = expected_output.get("premium") if isinstance(expected_output, dict) else None
    return Evaluation(
        name="金额校验", value=(got == exp), data_type="BOOLEAN",
        comment=f"{got} vs 期望 {exp}",
    )


EVALUATORS = [amount_check]


def main():
    from eddplatform.evals.adapters import langfuse as lf

    host = os.environ.get("LANGFUSE_HOST", "http://localhost:3100")
    print(f"Langfuse: {host}")
    lf.sync_dataset(DATASET)
    print(f"✓ 已 sync dataset「{DATASET.name}」({len(DATASET.cases)} 用例)")

    for rn in ("insurance-v1", "insurance-v2"):   # 让流程可重复执行
        lf.delete_run(DATASET.name, rn)

    r1 = lf.run_version(DATASET.name, "insurance-v1", system_v1, EVALUATORS)
    print(f"✓ v1 run 完成: insurance-v1  (通过率 {_pass_rate(r1)})")
    r2 = lf.run_version(DATASET.name, "insurance-v2", system_v2, EVALUATORS)
    print(f"✓ v2 run 完成: insurance-v2  (通过率 {_pass_rate(r2)})")

    print("\n每条用例都带一棵轨迹：intent-service → quote-engine → dialog-agent(LLM) → memory-service")
    print("对比 →", lf.compare_hint(host, DATASET.name, "insurance-v1", "insurance-v2"))


def _pass_rate(result) -> str:
    items = getattr(result, "item_results", None) or getattr(result, "items", None) or []
    passed = total = 0
    for it in items:
        for e in getattr(it, "evaluations", None) or []:
            v = e.get("value") if isinstance(e, dict) else getattr(e, "value", None)
            total += 1
            if v is True or v == 1:
                passed += 1
    return f"{passed}/{total}" if total else "?"


if __name__ == "__main__":
    main()
