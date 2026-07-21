"""EDD ↔ pydantic-evals 桥接（把这个文件原样复制进你的评估程序目录即可）。

项目开发者**只写标准 pydantic-evals**（Case / Dataset / evaluators / task 函数，
用法见 https://ai.pydantic.dev/evals/ ），最后一行交给本桥：

    from edd_bridge import serve

    dataset = Dataset(name="capital_quiz", cases=[...], evaluators=[...])

    async def task(inputs): ...          # 驱动被评系统，返回输出

    serve("my-eval", [(dataset, task)])  # workflow 名 = 队列名（平台用例库里配同名）

桥做的事：起 Temporal worker 认领队列，收 EDD 的 RunCaseInput{dataset, case}
（两个 name），在注册的 Dataset 里找到该 case → 用 pydantic-evals 跑单用例评估
→ 把报告映射成 EDD 的 CaseResultOut：

- assertions 全 True → passed；有 False → failed（detail=未通过项+原因）
- scores（数值型评估器输出）与 metrics（task 里 increment_eval_metric 的值 +
  task_duration_s）原样带回；
- task 里 ``raise Skip("原因")`` → skipped（该版本不适用，对比时剔除）；
- task/评估器自身异常、dataset/case 找不到 → ApplicationError → 平台记 error
  （评估链路问题）。

环境变量：TEMPORAL_ADDRESS（默认 host.k3d.internal:7233）、EVAL_WORKFLOW
（可覆盖 serve 的 workflow 名）。
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "host.k3d.internal:7233")
CASE_TIMEOUT_MIN = int(os.environ.get("EVAL_CASE_TIMEOUT_MIN", "4"))


# --- EDD 契约（与平台 runtime/temporal/shared.py 对齐，勿改字段名）------------
@dataclass
class RunCaseInput:
    run_id: str
    namespace: str
    dataset: str                       # 用例集 name
    case: str                          # 用例 name


@dataclass
class CaseResultOut:
    case_id: str                       # = 用例 name
    status: str = "passed"             # passed | failed | error | skipped
    scores: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    detail: str = ""
    trace_url: str | None = None


class Skip(Exception):
    """task 内抛出 → 该用例在此版本不适用（EDD 记 skipped，对比时剔除）。"""


_REGISTRY: dict[str, tuple] = {}       # dataset name -> (Dataset, task)


@activity.defn(name="edd_run_case")
async def _run_case(inp: RunCaseInput) -> CaseResultOut:
    from pydantic_evals import Dataset

    entry = _REGISTRY.get(inp.dataset)
    if entry is None:
        raise ApplicationError(
            f"未知用例集 dataset={inp.dataset!r}（本评估程序注册了: {sorted(_REGISTRY)}）"
            "——EDD 用例库 name 与评估代码不对应", non_retryable=True)
    ds, task = entry
    case = next((c for c in ds.cases if c.name == inp.case), None)
    if case is None:
        raise ApplicationError(
            f"用例集 {inp.dataset!r} 里没有 case={inp.case!r}"
            f"（已定义: {[c.name for c in ds.cases]}）"
            "——EDD 用例 name 与评估代码不对应", non_retryable=True)

    sub = Dataset(name=ds.name, cases=[case], evaluators=list(ds.evaluators))
    report = await sub.evaluate(task, progress=False, max_concurrency=1)

    # task 自身异常：Skip → skipped；其它 → 评估链路错误
    if report.failures:
        f = report.failures[0]
        msg = f.error_message or "task 执行失败"       # 形如 "异常类名: 消息"
        if msg.startswith("Skip:"):
            return CaseResultOut(case_id=inp.case, status="skipped",
                                 detail=msg.split(":", 1)[-1].strip())
        raise ApplicationError(f"task 执行失败: {msg[:400]}", non_retryable=True)

    rc = report.cases[0]
    if rc.evaluator_failures:
        errs = "; ".join(str(getattr(e, "error_message", e))[:200]
                         for e in rc.evaluator_failures)
        raise ApplicationError(f"评估器自身失败: {errs}", non_retryable=True)

    failures = [f"{name}: {res.reason or '未通过'}"
                for name, res in rc.assertions.items() if not res.value]
    scores = {name: float(res.value) for name, res in rc.scores.items()}
    metrics = {**{k: float(v) for k, v in rc.metrics.items()},
               "task_duration_s": round(rc.task_duration, 3)}
    return CaseResultOut(
        case_id=inp.case,
        status="failed" if failures else "passed",
        scores=scores, metrics=metrics,
        detail="；".join(failures),
    )


def serve(workflow_name: str, entries: list) -> None:
    """阻塞运行 worker。``entries`` = [(pydantic_evals.Dataset, task 函数), ...]。"""
    wf_name = os.environ.get("EVAL_WORKFLOW") or workflow_name
    for ds, task in entries:
        if not getattr(ds, "name", None):
            raise ValueError("Dataset 必须有 name（EDD 用它对应用例库）")
        _REGISTRY[ds.name] = (ds, task)

    class _EddRunCaseWorkflow:
        @workflow.run
        async def run(self, inp: RunCaseInput) -> CaseResultOut:
            return await workflow.execute_activity(
                _run_case, inp,
                start_to_close_timeout=timedelta(minutes=CASE_TIMEOUT_MIN),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )

    wf_cls = workflow.defn(name=wf_name, sandboxed=False)(_EddRunCaseWorkflow)

    async def _main() -> None:
        client = await Client.connect(TEMPORAL_ADDRESS)
        print(f"[edd_bridge] 已连接 {TEMPORAL_ADDRESS}，queue={wf_name}，"
              f"datasets={ {d: [c.name for c in e[0].cases] for d, e in _REGISTRY.items()} }",
              flush=True)
        async with Worker(client, task_queue=wf_name,
                          workflows=[wf_cls], activities=[_run_case]):
            await asyncio.Event().wait()

    asyncio.run(_main())
