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
        EvalArgs,
        OutcomeOut,
        RunCaseInput,
        RunTaskInput,
        RunTaskOutput,
        ScriptArgs,
    )

_ROLE = {"start_system": "system", "start_eval_program": "eval"}


@workflow.defn
class RunTaskWorkflow:
    @workflow.run
    async def run(self, inp: RunTaskInput) -> RunTaskOutput:
        out = RunTaskOutput(namespace=inp.namespace, status="up")
        # 部署类活动不做盲重试（避免重复部署）；给足超时（构建+helm --wait）
        opts = dict(
            start_to_close_timeout=timedelta(minutes=10),
            retry_policy=RetryPolicy(maximum_attempts=1),
        )

        for i, pc in enumerate(inp.preconditions):
            name = pc.name or f"{pc.kind}-{i}"
            try:
                if pc.kind in ("start_system", "start_eval_program"):
                    if not pc.git_url or not pc.ref:
                        raise ValueError(f"{pc.kind} 需要 git_url 和 ref")
                    role = _ROLE[pc.kind]
                    d = await workflow.execute_activity_method(
                        TaskActivities.deploy_repo,
                        DeployArgs(pc.git_url, pc.ref, name, inp.namespace, role, pc.path or "."),
                        **opts,
                    )
                    out.releases.append(d.release)
                    # 版本标签按前置条件名记（一个任务可拉多个系统单元，如 3 进程 3 条）
                    out.versions[name] = d.ref
                    out.outcomes.append(OutcomeOut(pc.kind, name, "ok", ref=d.ref, images=d.images))
                elif pc.kind == "custom_script":
                    if not pc.script:
                        raise ValueError("custom_script 需要 script")
                    await workflow.execute_activity_method(
                        TaskActivities.run_script, ScriptArgs(pc.script, inp.namespace), **opts
                    )
                    out.outcomes.append(OutcomeOut(pc.kind, name, "ok"))
                else:
                    raise ValueError(f"未知前置条件类型: {pc.kind}")
            except (ActivityError, ValueError) as e:
                out.status = "failed"
                out.outcomes.append(OutcomeOut(pc.kind, name, "failed", detail=str(e)))
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
            for case in inp.cases:
                try:
                    r = await workflow.execute_child_workflow(
                        inp.eval_code,
                        RunCaseInput(run_id=inp.run_id, namespace=inp.namespace, case=case),
                        id=f"{workflow.info().workflow_id}-case-{case.case_id}",
                        task_queue=inp.eval_code,
                        result_type=CaseResultOut,
                        execution_timeout=timedelta(minutes=5),
                    )
                    out.case_results.append(r)
                except Exception as e:  # noqa: BLE001 —— 单用例失败不拖垮整场
                    cause = e
                    while getattr(cause, "cause", None) is not None:
                        cause = cause.cause
                    out.case_results.append(
                        CaseResultOut(case_id=case.case_id, status="error",
                                      detail=str(getattr(cause, "message", None) or cause)))
        return out
