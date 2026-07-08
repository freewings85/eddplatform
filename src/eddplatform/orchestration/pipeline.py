"""发布评估流水线（框架无关核心）：建 env → 跑 → 评 → 对比 → 销。

纯 Python，可离线跑通。真实底座用 Temporal 编排（见 temporal_workflow.py），把这里的
每一步登记成 activity；逻辑不变，只是换执行引擎。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from eddplatform.domain.models import (
    Comparison,
    Dataset,
    EvalResult,
    Module,
    Requirement,
    SystemVersion,
)
from eddplatform.evals.engine import Evaluator, compare, rollup_by_requirement, run
from eddplatform.orchestration.manifest import render_manifest
from eddplatform.orchestration.providers import EnvironmentProvider

# target_factory(version_label, manifest, env_id) -> 被评系统入口 Callable[inputs -> output]
TargetFactory = Callable[[str, dict, str], Callable[[Any], Any]]


@dataclass
class ReleaseEvaluationResult:
    comparison: Comparison
    baseline: EvalResult
    candidate: EvalResult


def _evaluate_version(
    version: SystemVersion,
    modules: list[Module],
    dataset: Dataset,
    evaluators: dict[str, Evaluator],
    target_factory: TargetFactory,
    provider: EnvironmentProvider,
) -> EvalResult:
    """为一个版本拉一次性环境、跑该版本适用的用例、评分，**跑完必销**。"""
    manifest = render_manifest(modules, version)
    env_id = provider.create(manifest, ttl_hours=2.0)
    try:
        target = target_factory(version.label, manifest, env_id)
        cases = [c for c in dataset.cases if c.enabled and c.applies_to(version.label)]
        return run(target, cases, evaluators)
    finally:
        provider.destroy(env_id)          # ephemeral：无论成败都销毁


def run_release_evaluation(
    *,
    modules: list[Module],
    baseline_version: SystemVersion,
    candidate_version: SystemVersion,
    dataset: Dataset,
    evaluators: dict[str, Evaluator],
    target_factory: TargetFactory,
    provider: EnvironmentProvider,
    requirements: Sequence[Requirement] | None = None,
) -> ReleaseEvaluationResult:
    """老新对比的完整编排：两个版本各评一次 → 对比（+ 可选需求级汇总）。"""
    baseline = _evaluate_version(baseline_version, modules, dataset, evaluators,
                                 target_factory, provider)
    candidate = _evaluate_version(candidate_version, modules, dataset, evaluators,
                                  target_factory, provider)
    cmp = compare(baseline, candidate)
    if requirements:
        cmp.by_requirement = rollup_by_requirement(baseline, candidate,
                                                    dataset.cases, requirements)
    return ReleaseEvaluationResult(comparison=cmp, baseline=baseline, candidate=candidate)
