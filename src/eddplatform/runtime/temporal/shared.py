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


@dataclass
class RunTaskInput:
    preconditions: list[PreconditionSpec]
    namespace: str
    eval_deploy: str | None = None     # 评估观测：发起方服务
    eval_target: str | None = None     # 评估观测：被测服务


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


def to_spec(pc: Precondition) -> PreconditionSpec:
    """领域 Precondition → Temporal 入参（去掉 pydantic，用纯数据类）。"""
    return PreconditionSpec(
        kind=pc.kind.value, name=pc.name or pc.kind.value,
        git_url=pc.git_url, ref=pc.ref, script=pc.script,
    )
