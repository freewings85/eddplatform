"""框架无关的评估：把系统当黑盒（入口 + 轨迹 + 中立评估器）。

pydantic-evals / Langfuse 只是可选适配器（evals/adapters/），不是硬依赖。
"""

from eddplatform.evals.engine import (  # noqa: F401
    Contains,
    EqualsExpected,
    EvalContext,
    Evaluator,
    LLMJudge,
    MaxDuration,
    Outcome,
    SpanPresent,
    build_evaluator,
    compare,
    run,
    select,
)
from eddplatform.evals.targets import CallableTarget, HttpTarget  # noqa: F401
