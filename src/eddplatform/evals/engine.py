"""中立评估接口 + 零依赖本地兜底评分器（**不是**生产引擎）。

生产评估引擎复用开源：**Langfuse**（见 evals/adapters/langfuse.py）——不自研。
本模块只提供两样东西：

1. **中立适配层（防锁定）**：``Target`` / ``EvalContext`` / ``Evaluator`` 协议。
   被评系统一律当黑盒：能从入口拿到 ``输入 -> 输出``（+ 可选 OTel 轨迹）就能评，
   无论它是 pydantic-ai、LangGraph 还是任意 HTTP 服务；评估引擎也可换
   （Langfuse / Promptfoo / DeepEval）而不动这层接口。
2. **本地兜底评分器**：``run`` / ``compare`` + 几个 code 评估器，纯 Python 零依赖，
   仅用于**离线开发 / CI 冒烟 / 没有 Langfuse 实例时**。生产走 Langfuse。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence, runtime_checkable

from eddplatform.domain.models import (
    Case,
    CaseResult,
    Comparison,
    EvalResult,
    EvaluatorDef,
    EvaluatorKind,
    MetricDelta,
    OutputType,
    Requirement,
    RequirementRollup,
)

# --------------------------------------------------------------------------- 上下文 / 结果
@dataclass
class EvalContext:
    """中立的评估上下文——不含任何框架类型。"""

    inputs: Any
    output: Any
    expected_output: Any = None
    metadata: dict = field(default_factory=dict)
    duration_s: float = 0.0
    spans: list[dict] = field(default_factory=list)      # OTel 轨迹（简化：{name, duration_ms, ...}）
    attributes: dict = field(default_factory=dict)


@dataclass
class Outcome:
    """单个评估器的产出。value 类型对应 output_type：bool→断言 / 数值→分数 / 字符串→标签。"""

    name: str
    output_type: OutputType
    value: bool | float | str
    passed: bool
    reason: str | None = None


@runtime_checkable
class Evaluator(Protocol):
    name: str

    def evaluate(self, ctx: EvalContext) -> Outcome: ...


# 可插拔的 LLM 评委客户端：(rubric, ctx, model, include_input) -> (score, reason)
JudgeClient = Callable[[str, EvalContext, "str | None", bool], "tuple[float, str]"]


# --------------------------------------------------------------------------- 工具
def select(obj: Any, path: str | None) -> Any:
    """极简 JSONPath：``$.a.b`` 走 dict 取子字段；None 返回整体。"""
    if path is None:
        return obj
    cur = obj
    for part in path.lstrip("$").lstrip(".").split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


# --------------------------------------------------------------------------- 内置评估器（纯 Python）
@dataclass
class EqualsExpected:
    """output（或其子字段）== expected_output（或其子字段）。"""

    name: str = "equals_expected"
    path: str | None = None

    def evaluate(self, ctx: EvalContext) -> Outcome:
        got, exp = select(ctx.output, self.path), select(ctx.expected_output, self.path)
        ok = got == exp
        return Outcome(self.name, OutputType.ASSERTION, ok, ok, f"{got!r} == {exp!r}")


@dataclass
class Contains:
    """output（或子字段）包含 needle。"""

    name: str
    needle: str
    path: str | None = None

    def evaluate(self, ctx: EvalContext) -> Outcome:
        hay = select(ctx.output, self.path)
        ok = self.needle in hay if hay is not None else False
        return Outcome(self.name, OutputType.ASSERTION, ok, ok)


@dataclass
class MaxDuration:
    """耗时 ≤ seconds。"""

    name: str
    seconds: float

    def evaluate(self, ctx: EvalContext) -> Outcome:
        ok = ctx.duration_s <= self.seconds
        return Outcome(self.name, OutputType.ASSERTION, ok, ok, f"{ctx.duration_s:.2f}s ≤ {self.seconds}s")


@dataclass
class SpanPresent:
    """轨迹里存在名字包含 name_contains 的 span（如某工具调用）。"""

    name: str
    name_contains: str

    def evaluate(self, ctx: EvalContext) -> Outcome:
        ok = any(self.name_contains in s.get("name", "") for s in ctx.spans)
        return Outcome(self.name, OutputType.ASSERTION, ok, ok)


@dataclass
class LLMJudge:
    """LLM 评委：按 rubric 打分（框架/厂商无关，模型调用走可插拔 client）。"""

    name: str
    rubric: str
    model: str | None = None
    threshold: float | None = None
    include_input: bool = True
    path: str | None = None
    client: JudgeClient | None = None

    def evaluate(self, ctx: EvalContext) -> Outcome:
        client = self.client or _no_judge_client
        score, reason = client(self.rubric, ctx, self.model, self.include_input)
        passed = True if self.threshold is None else score >= self.threshold
        return Outcome(self.name, OutputType.SCORE, float(score), passed, reason)


def _no_judge_client(*_args, **_kwargs):
    raise RuntimeError(
        "LLMJudge 需要一个模型客户端：run(..., judge_client=fn)，"
        "fn(rubric, ctx, model, include_input) -> (score, reason)。"
        "客户端可用任意厂商/框架实现（与被评系统的框架无关）。"
    )


# --------------------------------------------------------------------------- 从 EvaluatorDef 装配
_BUILTINS = {"EqualsExpected": EqualsExpected, "Contains": Contains,
             "MaxDuration": MaxDuration, "HasMatchingSpan": SpanPresent}


def build_evaluator(d: EvaluatorDef, judge_client: JudgeClient | None = None) -> Evaluator:
    """EvaluatorDef（可管理定义）→ 具体评估器实例。"""
    if d.kind == EvaluatorKind.LLM_JUDGE:
        return LLMJudge(name=d.name, rubric=d.rubric or "", model=d.model,
                        threshold=d.threshold, path=d.json_path, client=judge_client)
    if d.kind == EvaluatorKind.BUILTIN:
        if d.builtin_type == "MaxDuration":
            return MaxDuration(name=d.name, seconds=d.threshold or 3.0)
        if d.builtin_type == "HasMatchingSpan":
            return SpanPresent(name=d.name, name_contains=d.rule or "")
        if d.builtin_type == "Contains":
            return Contains(name=d.name, needle=d.rule or "", path=d.json_path)
        return EqualsExpected(name=d.name, path=d.json_path)
    # CUSTOM_CODE：脚手架里退化为 EqualsExpected；真实项目在此挂自定义可调用
    return EqualsExpected(name=d.name, path=d.json_path)


# --------------------------------------------------------------------------- 运行 / 对比
def run(
    target: Callable[[Any], Any],
    cases: Sequence[Case],
    evaluators: dict[str, Evaluator],
) -> EvalResult:
    """用例驱动跑一遍：对每个用例 target(inputs) → 评估器打分 → 汇总。"""
    results: list[CaseResult] = []
    score_sums: dict[str, float] = {}
    score_counts: dict[str, int] = {}
    dur_sum = 0.0

    for c in cases:
        t0 = time.perf_counter()
        output = target(c.inputs)
        dt = time.perf_counter() - t0
        dur_sum += dt
        ctx = EvalContext(inputs=c.inputs, output=output, expected_output=c.expected_output,
                          metadata=c.metadata, duration_s=dt)
        outs = [evaluators[n].evaluate(ctx) for n in c.evaluator_names if n in evaluators]
        passed = all(o.passed for o in outs) if outs else True
        assertions = {o.name: bool(o.value) for o in outs if o.output_type == OutputType.ASSERTION}
        scores = {o.name: float(o.value) for o in outs if o.output_type == OutputType.SCORE}
        labels = {o.name: str(o.value) for o in outs if o.output_type == OutputType.LABEL}
        for k, v in scores.items():
            score_sums[k] = score_sums.get(k, 0.0) + v
            score_counts[k] = score_counts.get(k, 0) + 1
        results.append(CaseResult(case_id=c.id, passed=passed, assertions=assertions,
                                   scores=scores, labels=labels))

    n = len(results) or 1
    metrics = {k: score_sums[k] / score_counts[k] for k in score_sums}
    metrics["avg_duration_s"] = dur_sum / n
    pass_rate = sum(r.passed for r in results) / n
    return EvalResult(pass_rate=pass_rate, metrics=metrics, case_results=results)


def rollup_by_requirement(
    baseline: EvalResult,
    candidate: EvalResult,
    cases: Sequence[Case],
    requirements: Sequence[Requirement],
) -> list[RequirementRollup]:
    """把用例级结果按 case.requirement_ids 卷到需求级；只算两版都跑过的用例。

    达标 = 该需求的验收用例在该版本全部通过。返回顺序随 ``requirements``，
    跳过没有共有验收用例的需求。
    """
    base = {r.case_id: r for r in baseline.case_results}
    cand = {r.case_id: r for r in candidate.case_results}
    common = base.keys() & cand.keys()
    case_by_id = {c.id: c for c in cases}

    out: list[RequirementRollup] = []
    for req in requirements:
        cids = [cid for cid in common
                if req.id in getattr(case_by_id.get(cid), "requirement_ids", [])]
        if not cids:
            continue
        out.append(RequirementRollup(
            requirement_id=req.id, title=req.title, external_key=req.external_key,
            total_cases=len(cids),
            baseline_passed=sum(1 for cid in cids if base[cid].passed),
            candidate_passed=sum(1 for cid in cids if cand[cid].passed),
        ))
    return out


def compare(baseline: EvalResult, candidate: EvalResult) -> Comparison:
    """两个评估结果对比；只统计两边都跑过的用例。"""
    base = {r.case_id: r for r in baseline.case_results}
    cand = {r.case_id: r for r in candidate.case_results}
    common = base.keys() & cand.keys()
    improved = sum(1 for k in common if cand[k].passed and not base[k].passed)
    regressed = sum(1 for k in common if base[k].passed and not cand[k].passed)
    unchanged = len(common) - improved - regressed

    metrics = [MetricDelta(metric="通过率", baseline=baseline.pass_rate, candidate=candidate.pass_rate)]
    for k in baseline.metrics.keys() & candidate.metrics.keys():
        metrics.append(MetricDelta(metric=k, baseline=baseline.metrics[k], candidate=candidate.metrics[k]))

    return Comparison(baseline_eval_id="", candidate_eval_id="", applicable_cases=len(common),
                      improved=improved, regressed=regressed, unchanged=unchanged, metrics=metrics)
