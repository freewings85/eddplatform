"""可选适配器：pydantic-evals（给 pydantic-ai 项目）。

**可选**——核心引擎不依赖它。装了才可用：``pip install -e '.[pydantic-evals]'``。
存在的意义：pydantic-ai 团队若已用 pydantic-evals 写了 Evaluator/LLMJudge，可直接复用。
其它框架（LangGraph 等）用 evals/engine.py 的中立引擎即可，无需本模块。
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from eddplatform.domain.models import Case as DomainCase


def available() -> bool:
    try:
        import pydantic_evals  # noqa: F401

        return True
    except ImportError:
        return False


def _require() -> None:
    if not available():
        raise RuntimeError(
            "该适配器需要 pydantic-evals：pip install -e '.[pydantic-evals]'。"
            "（非必需——中立引擎 evals/engine.py 不装也能跑。）"
        )


def to_dataset(cases: Iterable[DomainCase], evaluators: Iterable[Any]):
    """领域 Case + pydantic-evals 评估器 → pydantic-evals Dataset。"""
    _require()
    from pydantic_evals import Case as PECase  # type: ignore
    from pydantic_evals import Dataset as PEDataset  # type: ignore

    pe_cases = [
        PECase(name=c.name, inputs=c.inputs, expected_output=c.expected_output, metadata=c.metadata)
        for c in cases
    ]
    return PEDataset(name="eddplatform", cases=pe_cases, evaluators=list(evaluators))


def run(task: Callable[[Any], Any], cases: Iterable[DomainCase], evaluators: Iterable[Any]):
    """用 pydantic-evals 跑一遍，返回其 EvaluationReport。"""
    _require()
    return to_dataset(cases, evaluators).evaluate_sync(task)
