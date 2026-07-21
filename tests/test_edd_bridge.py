"""edd_bridge（pydantic-evals → EDD 契约映射）：四态 + 分数/指标透传。

桥文件是项目复制用的（examples/edd-unit-template/eval/edd_bridge.py），
这里按路径加载直接测 ``_run_case`` 的映射逻辑，不需要 Temporal server。
"""
import importlib.util
from pathlib import Path

import pytest
from temporalio.exceptions import ApplicationError

BRIDGE = (Path(__file__).resolve().parents[1]
          / "examples" / "edd-unit-template" / "eval" / "edd_bridge.py")


@pytest.fixture()
def bridge():
    import sys
    spec = importlib.util.spec_from_file_location("edd_bridge_under_test", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod       # dataclass 解析字符串注解需能回查模块
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def registered(bridge):
    """标准 pydantic-evals 用法注册一个数据集（正是项目开发者要写的东西）。"""
    from dataclasses import dataclass

    from pydantic_evals import Case, Dataset
    from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

    @dataclass
    class Check(Evaluator):
        def evaluate(self, ctx: EvaluatorContext):
            return {
                "exact": EvaluationReason(value=ctx.output == ctx.expected_output,
                                          reason=f"期望 {ctx.expected_output!r} 实得 {ctx.output!r}"),
                "confidence": 0.9,
            }

    ds = Dataset(name="capital_quiz", cases=[
        Case(name="ok_case", inputs="France", expected_output="Paris"),
        Case(name="bad_case", inputs="Italy", expected_output="Rome"),
        Case(name="na_case", inputs="Atlantis", expected_output="-"),
        Case(name="boom_case", inputs="crash", expected_output="-"),
    ], evaluators=[Check()])

    async def task(inputs: str) -> str:
        from pydantic_evals.dataset import increment_eval_metric
        if inputs == "Atlantis":
            raise bridge.Skip("该版本没有这个国家")
        if inputs == "crash":
            raise RuntimeError("被评系统爆了")
        increment_eval_metric("input_tokens", 42)
        return {"France": "Paris", "Italy": "Milan"}[inputs]

    bridge._REGISTRY.clear()
    bridge._REGISTRY[ds.name] = (ds, task)
    return bridge


def _inp(bridge, case, dataset="capital_quiz"):
    return bridge.RunCaseInput(run_id="R-1", namespace="ns", dataset=dataset, case=case)


@pytest.mark.asyncio
async def test_passed_with_scores_and_metrics(registered):
    out = await registered._run_case(_inp(registered, "ok_case"))
    assert out.status == "passed" and out.case_id == "ok_case"
    assert out.scores == {"confidence": 0.9}
    assert out.metrics["input_tokens"] == 42.0
    assert "task_duration_s" in out.metrics


@pytest.mark.asyncio
async def test_failed_assertion_carries_reason(registered):
    out = await registered._run_case(_inp(registered, "bad_case"))
    assert out.status == "failed"
    assert "exact" in out.detail and "Milan" in out.detail


@pytest.mark.asyncio
async def test_skip_maps_to_skipped(registered):
    out = await registered._run_case(_inp(registered, "na_case"))
    assert out.status == "skipped"
    assert "没有这个国家" in out.detail


@pytest.mark.asyncio
async def test_task_crash_is_application_error(registered):
    with pytest.raises(ApplicationError, match="task 执行失败"):
        await registered._run_case(_inp(registered, "boom_case"))


@pytest.mark.asyncio
async def test_native_pydantic_evals_surface(bridge):
    """pydantic-evals 原生特性经桥不丢：case 级评估器、同步 task、labels 输出。"""
    from dataclasses import dataclass

    from pydantic_evals import Case, Dataset
    from pydantic_evals.evaluators import Evaluator, EvaluatorContext

    @dataclass
    class CaseLevel(Evaluator):
        def evaluate(self, ctx: EvaluatorContext):
            return {"case_level_ok": True}

    @dataclass
    class Labeler(Evaluator):
        def evaluate(self, ctx: EvaluatorContext):
            return {"tone": "polite"}          # str → label

    ds = Dataset(name="d", cases=[
        Case(name="c1", inputs="x", evaluators=[CaseLevel()]),
    ], evaluators=[Labeler()])

    def sync_task(inputs):                     # 同步 task 也是原生支持面
        return "y"

    bridge._REGISTRY.clear()
    bridge._REGISTRY["d"] = (ds, sync_task)
    out = await bridge._run_case(bridge.RunCaseInput("R", "ns", "d", "c1"))
    assert out.status == "passed"              # case 级断言生效
    assert "tone=polite" in out.detail         # labels 并进 detail


@pytest.mark.asyncio
async def test_unknown_dataset_or_case_is_application_error(registered):
    with pytest.raises(ApplicationError, match="未知用例集"):
        await registered._run_case(_inp(registered, "ok_case", dataset="nope"))
    with pytest.raises(ApplicationError, match="没有 case"):
        await registered._run_case(_inp(registered, "nope"))
