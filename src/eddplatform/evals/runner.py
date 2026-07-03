"""EvaluatorDef → Pydantic Evals 执行的集成点。

框架锁定 pydantic-ai；评估执行用 `pydantic-evals`（可选 extra: ``pip install -e '.[evals]'``）。
本模块 import 期不依赖 pydantic-evals；真正用到时才惰性导入，未安装则给出清晰提示。

映射（详见项目记忆「评估器定义模型」/ docs/）:
    返回值自动归类      bool → assertion, number → score, str → label
    CUSTOM_CODE        自定义 Evaluator 子类 + evaluate(ctx)
    LLM_JUDGE          LLMJudge(rubric, model, include_input, assertion=, score=)
    BUILTIN            EqualsExpected / Contains / MaxDuration / HasMatchingSpan / IsInstance
    读取输入           ctx.output / expected_output / inputs / metadata / duration / span_tree
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from eddplatform.domain.models import Case as DomainCase


def has_pydantic_evals() -> bool:
    try:
        import pydantic_evals  # noqa: F401

        return True
    except ImportError:
        return False


def _require():
    if not has_pydantic_evals():
        raise RuntimeError(
            "需要 pydantic-evals：pip install -e '.[evals]'（框架锁定 pydantic-ai）"
        )


def build_example_evaluators() -> dict[str, Any]:
    """示例：三种定义方式各一，演示 EvaluatorDef → pydantic-evals。"""
    _require()
    from dataclasses import dataclass

    from pydantic_evals.evaluators import (  # type: ignore
        Evaluator,
        EvaluatorContext,
        LLMJudge,
        MaxDuration,
    )

    @dataclass
    class AmountMatches(Evaluator):
        """自定义 code：报价金额 == 规则引擎期望值（bool → assertion）。"""

        def evaluate(self, ctx: EvaluatorContext) -> bool:
            expected = ctx.expected_output or {}
            got = ctx.output if isinstance(ctx.output, dict) else {}
            return got.get("premium") == expected.get("premium")

    clause_judge = LLMJudge(
        rubric="只依据真实条款，不得编造优惠/减免；1=严重编造，5=完全准确",
        include_input=True,
        assertion={"include_reason": True},        # 通过/不通过 + 理由
        score={"evaluation_name": "条款质量"},      # 另附 0-1 分
    )

    return {
        "金额校验": AmountMatches(),        # assertion
        "条款解释": clause_judge,           # assertion + score
        "延迟阈值": MaxDuration(seconds=3.0),  # assertion
    }


def build_dataset(cases: Iterable[DomainCase], evaluators: Iterable[Any]):
    """把领域层 Case + evaluators 组装成 pydantic-evals Dataset。"""
    _require()
    from pydantic_evals import Case as PECase  # type: ignore
    from pydantic_evals import Dataset as PEDataset  # type: ignore

    pe_cases = [
        PECase(
            name=c.name,
            inputs=c.inputs,
            expected_output=c.expected_output,
            metadata=c.metadata,
        )
        for c in cases
    ]
    return PEDataset(name="eddplatform", cases=pe_cases, evaluators=list(evaluators))


def run(task: Callable[[Any], Any], cases: Iterable[DomainCase], evaluators: Iterable[Any]):
    """跑一次评估，返回 pydantic-evals 的 EvaluationReport。

    ``task`` 是被评系统的入口：接受一个 case 的 inputs，返回系统输出。
    真实实现里 task 会打到沙箱里拉起的整系统入口（经 OTel 埋点 → Langfuse）。
    """
    _require()
    dataset = build_dataset(cases, evaluators)
    return dataset.evaluate_sync(task)
