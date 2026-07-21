"""业务子目录示例：**纯 pydantic-evals**，与官方用法完全一致，不碰 Temporal/EDD。

https://ai.pydantic.dev/evals/ —— 会写 pydantic-evals 就会写这个文件。
EDD 平台的用例库按 Dataset.name / Case.name 与这里一一对应。
"""
from dataclasses import dataclass

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext


@dataclass
class ExactMatch(Evaluator):
    def evaluate(self, ctx: EvaluatorContext):
        return {"exact": EvaluationReason(
            value=ctx.output == ctx.expected_output,
            reason=f"期望 {ctx.expected_output!r}，实得 {ctx.output!r}")}


dataset = Dataset(
    name="capital_quiz",                 # = EDD 用例库的 name
    cases=[
        Case(name="simple_case",         # = EDD 用例的 name
             inputs="What is the capital of France?",
             expected_output="Paris",
             metadata={"difficulty": "easy"}),
    ],
    evaluators=[ExactMatch()],
)


async def task(inputs: str) -> str:
    """驱动被评系统（HTTP 调它在集群内的服务名），返回输出。

    可用 pydantic_evals.dataset.increment_eval_metric("tokens", n) 记指标；
    该版本不适用时 `from edd_bridge import Skip; raise Skip("原因")`。
    """
    # import httpx
    # r = await httpx.AsyncClient().post("http://myservice:8080/ask", json={"q": inputs})
    return "Paris"
