"""Temporal workflow：一次 task 执行的编排。

EDD 启动 task → 提交本 workflow → 它按序执行前置条件活动（启动系统 / 启动评估程序 /
自定义脚本），全部就绪后让评估程序观测系统，产出运行记录（含结构化版本标签）。
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

# 活动/数据类的 import 放行（不进 workflow 沙箱的确定性限制）
with workflow.unsafe.imports_passed_through():
    from eddplatform.runtime.temporal.activities import TaskActivities
    from eddplatform.runtime.temporal.shared import (
        CaseResultOut,
        DeployArgs,
        DestroyArgs,
        EvalArgs,
        LogArgs,
        OutcomeOut,
        RunCaseInput,
        RunTaskInput,
        RunTaskOutput,
        ScriptArgs,
        WaitWorkerArgs,
        aggregate_attempts,
    )

_ROLE = {"start_system": "system", "start_eval_program": "eval"}


async def _maybe_destroy(inp) -> None:
    """任务选了「运行后销毁资源」：终态统一销毁一次性 namespace（尽力而为）。"""
    if not inp.destroy:
        return
    try:
        await workflow.execute_activity_method(
            TaskActivities.destroy_namespace, DestroyArgs(inp.namespace, inp.run_id),
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
    except Exception:  # noqa: BLE001 —— 销毁失败不改变运行结果
        await _log(inp.run_id, f"! 资源销毁失败——namespace {inp.namespace} 可能残留，需手动清理")


async def _log(run_id: str, line: str) -> None:
    """编排级控制台日志（尽力而为——日志失败绝不影响执行）。"""
    if not run_id:
        return
    try:
        await workflow.execute_activity_method(
            TaskActivities.append_run_log, LogArgs(run_id, line),
            start_to_close_timeout=timedelta(seconds=15),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )
    except Exception:  # noqa: BLE001
        pass


@workflow.defn
class RunTaskWorkflow:
    @workflow.run
    async def run(self, inp: RunTaskInput) -> RunTaskOutput:
        out = RunTaskOutput(namespace=inp.namespace, status="up")
        # 部署类活动不做盲重试（避免重复部署）；给足超时（构建+helm --wait）
        opts = dict(
            start_to_close_timeout=timedelta(minutes=20),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        seen_services: set[str] = set()
        for i, pc in enumerate(inp.preconditions):
            name = pc.name or f"{pc.kind}-{i}"
            try:
                if pc.kind in ("start_system", "start_eval_program"):
                    if not pc.git_url or not pc.ref:
                        raise ValueError(f"{pc.kind} 需要 git_url 和 ref")
                    role = _ROLE[pc.kind]
                    await _log(inp.run_id,
                               f"=== [{pc.kind}] {name}: 部署 {pc.git_url} @ {pc.ref} "
                               f"(单元目录 {pc.path or '.'}) ===")
                    d = await workflow.execute_activity_method(
                        TaskActivities.deploy_repo,
                        DeployArgs(pc.git_url, pc.ref, name, inp.namespace, role,
                                   pc.path or ".", inp.run_id, pc.env),
                        **opts,
                    )
                    # release 名以单元 chart/Chart.yaml 的 name 为准（部署器解析后回传）
                    if d.release in out.releases:
                        raise ValueError(
                            f"release 名重复: {d.release} —— 两个单元的 chart/Chart.yaml "
                            "声明了相同的 name，请改成互不相同（如 mainagent / sessionstore）")
                    # 服务名 = 集群内 DNS 名，须在本任务所有单元间唯一
                    overlap = seen_services & set(d.images.keys())
                    if overlap:
                        raise ValueError(
                            f"服务名撞名: {', '.join(sorted(overlap))} —— 服务名是集群内调用的 "
                            "DNS 名，必须在本任务的所有单元之间唯一")
                    seen_services.update(d.images.keys())
                    out.releases.append(d.release)
                    out.versions[d.release] = d.ref
                    out.outcomes.append(
                        OutcomeOut(pc.kind, d.release, "ok", ref=d.ref, images=d.images))
                elif pc.kind == "custom_script":
                    if not pc.script:
                        raise ValueError("custom_script 需要 script")
                    await workflow.execute_activity_method(
                        TaskActivities.run_script,
                        ScriptArgs(pc.script, inp.namespace, inp.run_id), **opts
                    )
                    out.outcomes.append(OutcomeOut(pc.kind, name, "ok"))
                else:
                    raise ValueError(f"未知前置条件类型: {pc.kind}")
            except (ActivityError, ValueError) as e:
                out.status = "failed"
                out.outcomes.append(OutcomeOut(pc.kind, name, "failed", detail=str(e)))
                await _log(inp.run_id, f"✗ 前置条件 [{pc.kind}] {name} 失败，终止后续步骤")
                break

        # 环境就绪 → 评估程序观测系统（真正「跑一次评估」的最小闭环）
        if out.status == "up" and inp.eval_deploy and inp.eval_target:
            out.result = await workflow.execute_activity_method(
                TaskActivities.run_eval,
                EvalArgs(inp.namespace, inp.eval_deploy, inp.eval_target),
                **opts,
            )

        # 逐用例分派：评估程序 worker 认领 eval_code 队列（方案 A：平台=client / 评估程序=worker）
        if out.status == "up" and inp.eval_code and inp.cases:
            # 队列预检：worker 没上线/名字配错 → 整场 fail fast，别让每条用例干等超时
            await _log(inp.run_id, f"=== 队列预检: 等评估 worker 认领队列 {inp.eval_code!r} ===")
            try:
                await workflow.execute_activity_method(
                    TaskActivities.wait_eval_worker,
                    WaitWorkerArgs(inp.eval_code, inp.eval_worker_wait_s, inp.run_id),
                    start_to_close_timeout=timedelta(seconds=inp.eval_worker_wait_s + 60),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
            except ActivityError as e:
                cause = e
                while getattr(cause, "cause", None) is not None:
                    cause = cause.cause
                out.status = "failed"
                out.outcomes.append(OutcomeOut(
                    "eval_dispatch", inp.eval_code, "failed",
                    detail=str(getattr(cause, "message", None) or cause)))
                await _maybe_destroy(inp)
                return out
            total = len(inp.cases)
            reps = max(1, inp.runs_per_case)
            for i, case_name in enumerate(inp.cases, 1):
                await _log(inp.run_id,
                           f"▶ [{i}/{total}] 用例 {case_name} → child workflow "
                           f"{inp.eval_code} (dataset={inp.dataset_name}"
                           f"{f', 执行 {reps} 次' if reps > 1 else ''})")
                attempts: list[CaseResultOut] = []
                for t in range(1, reps + 1):
                    suffix = f"-t{t}" if reps > 1 else ""
                    try:
                        r = await workflow.execute_child_workflow(
                            inp.eval_code,
                            RunCaseInput(run_id=inp.run_id, namespace=inp.namespace,
                                         dataset=inp.dataset_name, case=case_name),
                            id=f"{workflow.info().workflow_id}-case-{case_name}{suffix}",
                            task_queue=inp.eval_code,
                            result_type=CaseResultOut,
                            execution_timeout=timedelta(minutes=5),
                        )
                    except Exception as e:  # noqa: BLE001 —— 单次失败不拖垮整场
                        cause = e
                        while getattr(cause, "cause", None) is not None:
                            cause = cause.cause
                        r = CaseResultOut(case_id=case_name, status="error",
                                          detail=str(getattr(cause, "message", None) or cause))
                    attempts.append(r)
                    if reps > 1:
                        await _log(inp.run_id,
                                   f"  · 第 {t}/{reps} 次: {r.status}"
                                   f"{' · ' + r.detail if r.status != 'passed' and r.detail else ''}")
                agg = aggregate_attempts(case_name, attempts)
                agg.program = inp.eval_code            # 报告按评估程序归组（界面分区展示）
                out.case_results.append(agg)
                mark = {"passed": "✓", "failed": "✗", "error": "!", "skipped": "→"}.get(
                    agg.status, "?")
                await _log(inp.run_id,
                           f"{mark} [{i}/{total}] 用例 {case_name} {agg.status}"
                           f"{' · ' + str(agg.scores) if agg.scores else ''}"
                           f"{' · ' + agg.detail if agg.detail else ''}")
        await _maybe_destroy(inp)
        return out
