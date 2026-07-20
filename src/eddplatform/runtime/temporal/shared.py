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


@dataclass
class ScriptArgs:
    script: str
    namespace: str


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


# --- RunCase 契约（平台 ↔ 评估程序 worker）----------------------------------
# 评估程序仓实现一个 workflow：名字 = task queue = EvalProgram.code，
# 入参 RunCaseInput，出参 CaseResultOut。平台逐 case 以 child workflow 分派。
@dataclass
class CaseSpec:
    case_id: str
    name: str = ""
    inputs: str = ""                   # JSON 串或原文（turns 等）
    expected: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class RunCaseInput:
    run_id: str
    namespace: str
    case: CaseSpec


@dataclass
class CaseResultOut:
    case_id: str
    status: str = "passed"             # passed | failed | error
    scores: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    detail: str = ""
    trace_url: str | None = None


@dataclass
class RunTaskInput:
    preconditions: list[PreconditionSpec]
    namespace: str
    eval_deploy: str | None = None     # 评估观测：发起方服务
    eval_target: str | None = None     # 评估观测：被测服务
    run_id: str = ""                   # 平台侧 RunRecord id
    eval_code: str | None = None       # 评估程序 code（RunCase workflow 名/队列）
    cases: list[CaseSpec] = field(default_factory=list)


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
    """领域 Precondition → Temporal 入参（去掉 pydantic，用纯数据类）。"""
    return PreconditionSpec(
        kind=pc.kind.value, name=pc.name or pc.kind.value,
        git_url=pc.git_url, ref=pc.ref, script=pc.script,
        path=pc.path or ".",
    )
