"""Temporal workflow/活动的输入输出类型（纯数据类，可被 Temporal 默认 JSON 转换器序列化）。

单独一个纯模块：workflow 沙箱可安全 import，不牵扯 subprocess/k8s 等重依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eddplatform.domain.models import Precondition

TASK_QUEUE = "edd-task-queue"


# --- 活动入参 ---------------------------------------------------------------
@dataclass
class DeployArgs:
    git_url: str
    ref: str
    release: str
    namespace: str
    role: str                          # system | eval
    path: str = "."                    # 仓库内单元目录（一个仓库可含多个可部署单元）
    run_id: str = ""                   # 控制台日志归属的运行（空=不落库）
    env: str | None = None             # 部署配置（.env.eval 内容，helm 以 eddEnv/eddEnvVars 注入）


@dataclass
class ScriptArgs:
    script: str
    namespace: str
    run_id: str = ""


@dataclass
class WaitWorkerArgs:
    queue: str                         # 评估 workflow 名 = 队列名
    timeout_s: int = 90                # 等 worker 上线的宽限期（评估程序 pod 启动需要时间）
    run_id: str = ""


@dataclass
class LogArgs:
    """workflow 侧写一行控制台日志（逐用例分派等编排级事件）。"""
    run_id: str
    line: str


@dataclass
class DestroyArgs:
    """运行结束后销毁本次创建的 k8s 资源（整个一次性 namespace）。"""
    namespace: str
    run_id: str = ""


@dataclass
class EvalArgs:
    namespace: str
    eval_deploy: str                   # 评估程序里发起观测的服务（如 judge）
    target: str                        # 被观测的系统服务（如 quote）


# --- 活动出参 ---------------------------------------------------------------
@dataclass
class DeployOut:
    role: str
    release: str
    ref: str
    images: dict[str, str] = field(default_factory=dict)
    pods: list[str] = field(default_factory=list)


# --- workflow 入参 / 出参 ---------------------------------------------------
@dataclass
class PreconditionSpec:
    kind: str                          # start_system | start_eval_program | custom_script
    name: str
    git_url: str | None = None
    ref: str | None = None
    script: str | None = None
    path: str = "."                    # 仓库内单元目录
    env: str | None = None             # 部署配置（.env.eval 内容）


# --- RunCase 契约（平台 ↔ 评估程序 worker）----------------------------------
# 评估程序仓实现一个 workflow：名字 = task queue = 用例库配置的 workflow 名，
# 入参 RunCaseInput（**只传用例集 name + 用例 name**——用例的实际定义/输入/期望/
# 判定逻辑全部在评估代码仓里，平台只管映射），出参 CaseResultOut。
@dataclass
class RunCaseInput:
    run_id: str
    namespace: str
    dataset: str                       # 用例集 name（与评估代码里的 dataset 对应）
    case: str                          # 用例 name（评估代码按它找到自己定义的 case）


@dataclass
class CaseGroup:
    """一个用例分组的执行参数：用例集 name + 该组的评估 workflow + 用例清单。"""

    dataset: str
    workflow: str                      # 评估 workflow 名 = 队列名（来自用例库配置）
    cases: list[str] = field(default_factory=list)


@dataclass
class CaseResultOut:
    case_id: str                       # = 用例 name（回传对齐用）
    # passed=通过 | failed=没通过(被评系统的问题,计回归) |
    # error=评估过程失败(评估链路的问题,对比时剔除) | skipped=该版本不适用(剔除)
    status: str = "passed"
    scores: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    detail: str = ""
    trace_url: str | None = None
    report: str = ""                   # pydantic-evals 原生报告表（文本，评估程序渲染）
    program: str = ""                  # 处理本用例的评估程序(workflow 名)——平台回填
    dataset: str = ""                  # 所属用例集 name——平台回填（多用例库任务区分来源）
    attempts: int = 1                  # 本用例实际执行次数（任务「每用例执行次数」）
    passed_attempts: int = 1           # 其中通过的次数（attempts>1 时界面显示 n/N）


def aggregate_attempts(case_name: str, attempts: list[CaseResultOut]) -> CaseResultOut:
    """把同一用例的多次执行聚合成一条结果（LLM 非确定性：一次过≠稳定过）。

    - status：任一 failed → failed；否则任一 error → error；全 skipped → skipped；
      其余 → passed（全部通过才算过——宽松口径由 scores.pass_rate 自行判断）。
    - scores：取最后一次的分数，多次时附 ``pass_rate``（通过次数/总次数）。
    - metrics：数值指标按次取均值（如 task_duration_s）。
    - detail/report：逐次拼接，失败的那次细节不丢。
    """
    n = len(attempts)
    if n == 1:
        one = attempts[0]
        one.attempts = 1
        one.passed_attempts = 1 if one.status == "passed" else 0
        return one
    statuses = [a.status for a in attempts]
    passed = sum(1 for s in statuses if s == "passed")
    if "failed" in statuses:
        status = "failed"
    elif "error" in statuses:
        status = "error"
    elif all(s == "skipped" for s in statuses):
        status = "skipped"
    else:
        status = "passed"

    scores: dict[str, float] = dict(attempts[-1].scores)
    scores["pass_rate"] = round(passed / n, 2)
    metric_keys = {k for a in attempts for k in a.metrics}
    metrics = {k: round(sum(a.metrics[k] for a in attempts if k in a.metrics)
                        / max(1, sum(1 for a in attempts if k in a.metrics)), 3)
               for k in metric_keys}

    marks = {"passed": "✓", "failed": "✗", "error": "!", "skipped": "→"}
    seq = ",".join(marks.get(s, "?") for s in statuses)
    fail_details = [f"第{i}次: {a.detail}" for i, a in enumerate(attempts, 1)
                    if a.status != "passed" and a.detail]
    detail = f"{passed}/{n} 次通过 · 各次: {seq}"
    if fail_details:
        detail += " · " + "；".join(fail_details[:3])

    reports = [f"----- 第 {i}/{n} 次（{a.status}）-----\n{a.report}"
               for i, a in enumerate(attempts, 1) if a.report]
    trace_urls = [a.trace_url for a in attempts if a.trace_url]
    return CaseResultOut(
        case_id=case_name, status=status, scores=scores, metrics=metrics,
        detail=detail, trace_url=trace_urls[-1] if trace_urls else None,
        report="\n".join(reports), program=attempts[-1].program,
        dataset=attempts[-1].dataset, attempts=n, passed_attempts=passed,
    )


@dataclass
class RunTaskInput:
    preconditions: list[PreconditionSpec]
    namespace: str
    eval_deploy: str | None = None     # 评估观测：发起方服务
    eval_target: str | None = None     # 评估观测：被测服务
    run_id: str = ""                   # 平台侧 RunRecord id
    eval_code: str | None = None       # 旧单库格式：评估 workflow 名（来自用例库配置）
    eval_worker_wait_s: int = 90       # 队列预检：等评估 worker 上线的宽限期
    dataset_name: str = ""             # 旧单库格式：用例集 name
    cases: list[str] = field(default_factory=list)   # 旧单库格式：用例 name 清单
    case_groups: list[CaseGroup] = field(default_factory=list)  # 用例分组（非空时优先）
    destroy: bool = False              # 运行结束后销毁 namespace（任务选项）
    runs_per_case: int = 1             # 每用例执行次数（>1 时聚合出 pass_rate，全过才算过）
    case_concurrency: int = 4          # 用例并发数（gather+信号量；1=串行）


@dataclass
class OutcomeOut:
    kind: str
    name: str
    status: str                        # ok | failed
    ref: str | None = None
    images: dict[str, str] = field(default_factory=dict)
    detail: str = ""


@dataclass
class RunTaskOutput:
    namespace: str
    status: str                        # up | failed
    versions: dict[str, str] = field(default_factory=dict)   # {system: sha, eval: sha}
    outcomes: list[OutcomeOut] = field(default_factory=list)
    releases: list[str] = field(default_factory=list)
    result: dict = field(default_factory=dict)               # 评估观测结果
    case_results: list[CaseResultOut] = field(default_factory=list)


def to_spec(pc: Precondition) -> PreconditionSpec:
    """领域 Precondition → Temporal 入参（去掉 pydantic，用纯数据类）。

    部署 ref 用固化的 ``commit``（钉死可复现）；缺 commit 时退回 ``branch``。
    """
    return PreconditionSpec(
        kind=pc.kind.value, name=pc.name or pc.kind.value,
        git_url=pc.git_url, ref=pc.commit or pc.branch, script=pc.script,
        path=pc.path or ".", env=pc.env,
    )
