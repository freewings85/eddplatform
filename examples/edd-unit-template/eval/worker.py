"""评估程序示例：标准 pydantic-evals + edd_bridge.serve() 一行接入 EDD。

开发者只需要会 pydantic-evals（https://ai.pydantic.dev/evals/）：
Case/Dataset/Evaluator 该怎么写怎么写，本文件就是全部需要的结构。
EDD 平台的用例库按 Dataset.name / Case.name 与这里一一对应。
"""
from dataclasses import dataclass

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from edd_bridge import serve  # , Skip   # task 里 raise Skip("原因") → 该版本不适用


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

    可用 pydantic_evals.dataset.increment_eval_metric("tokens", n) 记指标。
    """
    # import httpx
    # r = await httpx.AsyncClient().post("http://myservice:8080/ask", json={"q": inputs})
    return "Paris"


if __name__ == "__main__":
    serve("capital-quiz-eval", [(dataset, task)])   # workflow 名=队列名（用例库里配同名）
