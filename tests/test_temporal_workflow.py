"""Temporal 编排：用 temporalio 自带 WorkflowEnvironment 跑真 workflow（无需 docker
server），证明与 pipeline.run_release_evaluation（纯 Python）语义等价。"""

from __future__ import annotations

import asyncio

import pytest
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment

from eddplatform.orchestration import temporal_workflow as tw
from eddplatform.orchestration.providers import MockProvider
# 仓库无 tests/__init__.py，pytest 把 tests/ 放上 sys.path → 裸名导入（见 test_models.py 先例）
from release_sample import (
    DATASET, EVALUATORS, MODULES, REQUIREMENTS, V1, V2, target_factory,
)


async def _run(request, provider):
    async with await WorkflowEnvironment.start_time_skipping(
            data_converter=pydantic_data_converter) as env:
        return await tw.run_release_evaluation_via_temporal(
            env.client, request=request, provider=provider,
            target_factory=target_factory, evaluators=EVALUATORS, modules=MODULES)


def test_temporal_matches_pure_python():
    """Temporal 版对比结果与纯 Python 版一致：改善 1 / 回归 0 / 共有 3。"""
    provider = MockProvider()
    req = tw.ReleaseEvalRequest(baseline_version=V1, candidate_version=V2, dataset=DATASET,
                                requirements=REQUIREMENTS)
    res = asyncio.run(_run(req, provider))
    assert res.comparison.improved == 1
    assert res.comparison.regressed == 0
    assert res.comparison.applicable_cases == 3
    r101 = next(r for r in res.comparison.by_requirement if r.requirement_id == "R-101")
    assert r101.baseline_passed == 1 and r101.candidate_passed == 2
    assert provider.live_count() == 0            # ephemeral：默认销毁


def test_temporal_keeps_environments_when_cleanup_false():
    provider = MockProvider()
    req = tw.ReleaseEvalRequest(baseline_version=V1, candidate_version=V2, dataset=DATASET,
                                cleanup=False)
    asyncio.run(_run(req, provider))
    assert provider.live_count() == 2            # 两个版本环境都保留


def test_temporal_destroys_even_when_evaluation_raises():
    """评估步抛错也要销毁环境（ephemeral 补偿）。"""
    class BoomFactory:
        def __call__(self, label, manifest, env_id):
            def boom(inputs):
                raise RuntimeError("target 挂了")
            return boom

    provider = MockProvider()
    req = tw.ReleaseEvalRequest(baseline_version=V1, candidate_version=V2, dataset=DATASET)

    async def go():
        async with await WorkflowEnvironment.start_time_skipping(
                data_converter=pydantic_data_converter) as env:
            with pytest.raises(Exception):
                await tw.run_release_evaluation_via_temporal(
                    env.client, request=req, provider=provider,
                    target_factory=BoomFactory(), evaluators=EVALUATORS, modules=MODULES)
    asyncio.run(go())
    assert provider.live_count() == 0            # 抛错后仍销毁（至少 baseline 那个）
