"""Temporal 编排（live）：把 pipeline.run_release_evaluation 的逻辑搬到真实 Temporal
workflow + activities，逻辑不变、只换执行引擎（可重试 / 可观测 / 可断点续跑）。

关键设计：
- 副作用步（建 env / 跑评估 / 销 env）= class-instance activity，把不可序列化的
  provider / target_factory / evaluators / modules 闭包进 worker 侧（不进 workflow 输入）。
- 纯确定性步（compare / rollup / 用例过滤）留在 workflow，结果与 pipeline 逐字段一致。
- workflow 输入/输出是 pydantic 模型，用 pydantic_data_converter 序列化。

本模块必须 import-safe（workflow sandbox 会重新 import 它）：顶层只定义、不执行。
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta

from pydantic import BaseModel
from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

# workflow 内会用到的应用/三方符号——sandbox 里放行透传（避免重复执行/被限制）
with workflow.unsafe.imports_passed_through():
    from eddplatform.domain.models import (
        Case, Comparison, Dataset, EvalResult, Requirement, SystemVersion,
    )
    from eddplatform.evals.engine import compare, rollup_by_requirement, run
    from eddplatform.orchestration.manifest import DEFAULT_OTEL_ENDPOINT, render_manifest
    from eddplatform.orchestration.pipeline import ReleaseEvaluationResult

TASK_QUEUE = "edd-release-eval"

# 匹配纯 Python pipeline 的「零重试」语义：被评系统(target)确定性失败即失败，
# 不重试——否则死循环，且违背与 run_release_evaluation 的等价性。
NO_RETRY = RetryPolicy(maximum_attempts=1)

# 基础设施活动（建/销 env）容忍瞬时故障，有界重试；被评系统(evaluate)不重试(见 NO_RETRY)。
INFRA_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
)


def available() -> bool:
    try:
        import temporalio  # noqa: F401

        return True
    except ImportError:
        return False


# --------------------------------------------------------------------------- 数据契约
class ReleaseEvalRequest(BaseModel):
    """workflow 输入（全可序列化）。modules/provider/target_factory/evaluators 由 worker 绑定。"""

    baseline_version: SystemVersion
    candidate_version: SystemVersion
    dataset: Dataset
    requirements: list[Requirement] = []
    cleanup: bool = True
    otel_endpoint: str = DEFAULT_OTEL_ENDPOINT
    ttl_hours: float = 2.0


class ReleaseEvalOutcome(BaseModel):
    comparison: Comparison
    baseline: EvalResult
    candidate: EvalResult


# --------------------------------------------------------------------------- Activities
class ReleaseEvalActivities:
    """activity 方法闭包进不可序列化依赖（worker 侧构造）。provider/target_factory 可能
    同步阻塞（kubectl/HTTP/LLM）→ 用 asyncio.to_thread 包，避免堵 event loop。"""

    def __init__(self, provider, target_factory, evaluators, modules):
        self.provider = provider
        self.target_factory = target_factory
        self.evaluators = evaluators
        self.modules = modules

    @activity.defn
    async def create_env(self, version: SystemVersion, otel_endpoint: str,
                         ttl_hours: float) -> str:
        manifest = render_manifest(self.modules, version, otel_endpoint=otel_endpoint)
        return await asyncio.to_thread(self.provider.create, manifest, ttl_hours)

    @activity.defn
    async def evaluate_version(self, version: SystemVersion, cases: list[Case],
                               env_id: str, otel_endpoint: str) -> EvalResult:
        manifest = render_manifest(self.modules, version, otel_endpoint=otel_endpoint)
        target = self.target_factory(version.label, manifest, env_id)
        return await asyncio.to_thread(run, target, cases, self.evaluators)

    @activity.defn
    async def destroy_env(self, env_id: str) -> None:
        await asyncio.to_thread(self.provider.destroy, env_id)


# --------------------------------------------------------------------------- Workflow
@workflow.defn
class ReleaseEvaluationWorkflow:
    @workflow.run
    async def run(self, req: ReleaseEvalRequest) -> ReleaseEvalOutcome:
        baseline = await self._eval_one(req.baseline_version, req)
        candidate = await self._eval_one(req.candidate_version, req)
        cmp = compare(baseline, candidate)
        if req.requirements:
            cmp.by_requirement = rollup_by_requirement(
                baseline, candidate, req.dataset.cases, req.requirements)
        return ReleaseEvalOutcome(comparison=cmp, baseline=baseline, candidate=candidate)

    async def _eval_one(self, version: SystemVersion, req: ReleaseEvalRequest) -> EvalResult:
        cases = [c for c in req.dataset.cases
                 if c.enabled and c.applies_to(version.label)]
        env_id = await workflow.execute_activity(
            ReleaseEvalActivities.create_env,
            args=[version, req.otel_endpoint, req.ttl_hours],
            start_to_close_timeout=timedelta(minutes=10), retry_policy=INFRA_RETRY)
        try:
            return await workflow.execute_activity(
                ReleaseEvalActivities.evaluate_version,
                args=[version, cases, env_id, req.otel_endpoint],
                start_to_close_timeout=timedelta(minutes=30), retry_policy=NO_RETRY)
        finally:
            if req.cleanup:                       # ephemeral：无论成败都销毁
                await workflow.execute_activity(
                    ReleaseEvalActivities.destroy_env, args=[env_id],
                    start_to_close_timeout=timedelta(minutes=5), retry_policy=INFRA_RETRY)


# --------------------------------------------------------------------------- Worker / runner
def build_worker(client: Client, task_queue: str, *, provider, target_factory,
                 evaluators, modules) -> Worker:
    """构造注册了 workflow + 绑定依赖的 activities 的 worker。"""
    acts = ReleaseEvalActivities(provider, target_factory, evaluators, modules)
    return Worker(client, task_queue=task_queue, workflows=[ReleaseEvaluationWorkflow],
                  activities=[acts.create_env, acts.evaluate_version, acts.destroy_env])


async def run_release_evaluation_via_temporal(
    client: Client, *, request: ReleaseEvalRequest, provider, target_factory,
    evaluators, modules, task_queue: str = TASK_QUEUE,
) -> ReleaseEvaluationResult:
    """便捷入口：起 worker → 执行 workflow → 包成 pipeline.ReleaseEvaluationResult（与纯
    Python 版同型，二者可互换）。activity 失败时 workflow 抛出的是 Temporal 的
    ``WorkflowFailureError``（包裹原始 activity 异常），不是原始的 ``RuntimeError``——
    从纯 Python 路径迁移过来的调用方需放宽 except 类型来捕获。"""
    worker = build_worker(client, task_queue, provider=provider,
                          target_factory=target_factory, evaluators=evaluators, modules=modules)
    async with worker:
        outcome = await client.execute_workflow(
            ReleaseEvaluationWorkflow.run, request,
            id=f"edd-release-{workflow_id_suffix()}", task_queue=task_queue)
    return ReleaseEvaluationResult(comparison=outcome.comparison,
                                   baseline=outcome.baseline, candidate=outcome.candidate)


def workflow_id_suffix() -> str:
    """workflow id 后缀。用 uuid4 保证并发唯一（在 activity/客户端侧，非 workflow 内，可用随机）。"""
    return uuid.uuid4().hex[:12]
