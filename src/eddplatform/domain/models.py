"""EddPlatform 领域模型。

对象关系（与 prototype/ 和 docs/ 一致）::

    System        被评系统（注册表；约定式部署直接用 git 仓库）
    EvalProgram   评估程序（独立 git 仓；workflow 名在其自身代码里）
    DatasetInfo ─< Case（纯注册记录：name 与评估代码里的 dataset/case 一一对应）
    Task          评估任务 = 用例清单 + 有序前置条件（评估内容全在评估代码仓）
    RunRecord     一次 task 执行（Temporal workflow 的平台侧记录）─< CaseRunResult
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, field_validator


# --------------------------------------------------------------------------- 枚举
class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# --------------------------------------------------------------------------- 系统 / 模块 / 版本
class Module(BaseModel):
    """一个服务/进程，绑定 Git 仓库 + Harbor 镜像。对应 Backstage Component。"""

    name: str
    git_url: str
    branch: str = "main"
    image: str                        # Harbor 镜像仓库路径
    dockerfile: str = "./Dockerfile"
    healthcheck: str = "/healthz"
    owner: str | None = None
    prod_tag: str | None = None


class System(BaseModel):
    id: str
    name: str
    owner: str | None = None
    description: str | None = None
    cases_git_url: str | None = None  # 用例仓库（git 管版本；导入/导出的对端）
    cases_branch: str = "main"        # 用例仓分支
    modules: list[Module] = []
    prod_version: str | None = None


class SystemProgram(BaseModel):
    """系统程序：被评系统的一个可部署 git 单元的**注册项**（名称 + git 地址 + 目录）。

    建评估任务时从这里下拉选择，分支/commit 在任务里固化——git 信息只登记一次。
    """

    id: str = ""                      # 空 = store 落库时生成（SP-0001）
    system_id: str = ""
    name: str
    git_url: str
    path: str = "."                   # 仓库内单元目录（一个仓库可含多个单元）
    env: str | None = None            # 部署配置默认值（.env.eval 内容；建任务时带出可改）
    owner: str | None = None

    @field_validator("git_url")
    @classmethod
    def _git_url_no_whitespace(cls, v: str) -> str:
        v = v.strip()
        if any(ch.isspace() for ch in v):
            raise ValueError("git 地址不能包含空白字符（检查是否粘贴了多余内容）")
        return v


class EvalProgram(BaseModel):
    """评估程序（评估代码库）——**独立于系统程序**的另一套 git 单元注册项。

    实现评估逻辑（怎么算分），按「build.sh + 标准 helm chart」约定被拉起来当 worker。
    它认领的 workflow 名/队列名写在**它自己的代码/配置里**（平台不登记）；
    用例库配置的 ``workflow`` 名与之一致即可对上。分支/commit 在任务里固化。
    """

    id: str = ""                      # 空 = store 落库时生成（EP-0001）
    system_id: str = ""
    name: str
    git_url: str
    path: str = "."                   # 仓库内单元目录（评估程序可与被评系统同仓不同目录）
    env: str | None = None            # 部署配置默认值（.env.eval 内容；建任务时带出可改）
    owner: str | None = None

    @field_validator("git_url")
    @classmethod
    def _git_url_no_whitespace(cls, v: str) -> str:
        v = v.strip()
        if any(ch.isspace() for ch in v):
            raise ValueError("git 地址不能包含空白字符（检查是否粘贴了多余内容）")
        return v


# --------------------------------------------------------------------------- 用例 / 用例集
class CaseTrace(BaseModel):
    """用例对应的线上轨迹：轻引用 + 可选的**归档数据**。

    轨迹本体在 Langfuse；担心被清理时可点「归档」把完整 trace JSON 拉回平台
    （并随用例导出进 git），将来 Langfuse 里没了也能查看。
    """

    ref: str | None = None                # Langfuse trace id（从 URL 解析，用户不直接填）
    url: str | None = None                # 直达轨迹视图的链接（host + id 拼）
    note: str | None = None               # 这条轨迹的问题简述
    data: dict | None = None              # 归档的完整 trace JSON（可选）
    archived_at: datetime | None = None   # 归档时间


class TagNode(BaseModel):
    """标签树节点（每系统一棵树）。case 用完整路径（如 ``业务/报价``）引用标签。"""

    id: str
    name: str                             # 单层名字，不含 "/"
    parent_id: str | None = None          # None = 根
    path: str = ""                        # 计算得到的完整路径（业务/报价）


class Case(BaseModel):
    """用例：**纯注册记录**——身份 + 元信息 + 轨迹关联。

    EDD 不携带、不理解任何评估内容（输入/期望/判定都定义在评估代码仓里）；
    执行时平台只把「用例集 name + 用例 name」传给评估 workflow，由评估代码
    按 name 找到自己定义的 case 跑一次评估。``name`` 是与评估代码对应的机器
    友好名（如 guide_platform_intro），``id`` 仅内部使用（= name）。
    """

    id: str = ""                          # 内部 id（落库时 = name）
    name: str                             # 与评估代码里 case 一一对应的名字
    description: str | None = None        # 用例意图/在测什么（人看的）
    tags: list[str] = []                  # 数据集内分组/筛选
    trace: CaseTrace | None = None        # 一条 case 对应一条轨迹（轻引用+归档）
    enabled: bool = True
    created_at: datetime | None = None    # store 自动维护
    updated_at: datetime | None = None    # store 自动维护

    @field_validator("name")
    @classmethod
    def _name_no_whitespace(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("用例 name 不能为空")
        if any(ch.isspace() for ch in v):
            raise ValueError("用例 name 不能包含空白字符（它是传给评估代码的标识）")
        return v


class DatasetInfo(BaseModel):
    """用例库注册项：一个系统可有多个用例库，用例按库分区。

    ``name`` 与评估代码里的 dataset 对应（执行时随用例 name 一起传入 workflow）。
    """

    id: str = ""                          # 内部 id（store 落库时生成，DS-0001）
    system_id: str = ""
    name: str
    description: str | None = None
    workflow: str | None = None           # 评这批用例的 RunCase workflow 名（=评估程序认领的队列）
    path: str | None = None               # 用例仓里对应的文件夹（git 导入/导出的锚点）


class GlobalSettings(BaseModel):
    """平台级基础设置（Langfuse 连接等）。"""

    langfuse_host: str | None = None          # 如 http://localhost:3100
    langfuse_public_key: str | None = None    # pk-lf-…
    langfuse_secret_key: str | None = None    # sk-lf-…


# --------------------------------------------------------------------------- 运行 / 结果
class RunRecord(BaseModel):
    """一次 task 执行（experiment）：Temporal workflow 的平台侧记录。"""

    id: str = ""                           # 空 = store 落库时生成（R-xxxxxxxx）
    system_id: str
    task_id: str
    task_name: str = ""
    status: RunStatus = RunStatus.RUNNING
    workflow_id: str = ""
    namespace: str = ""
    versions: dict[str, str] = {}          # {system: sha, eval: sha}
    outcomes: list[dict] = []              # 每条前置条件的 OutcomeOut dict
    case_stats: dict[str, int] = {}        # 用例结果汇总 {passed/failed/error/skipped: n}
    detail: str = ""                       # 失败原因等
    created_at: datetime | None = None
    finished_at: datetime | None = None


class CaseRunResult(BaseModel):
    """单用例评估结果（由评估程序 worker 经 RunCase workflow 返回）。"""

    case_id: str
    status: str = "passed"                 # passed | failed | error
    scores: dict[str, float] = {}
    metrics: dict[str, float] = {}
    detail: str = ""
    trace_url: str | None = None


# --------------------------------------------------------------------------- 任务前置条件
class PreconditionKind(str, Enum):
    """task 启动前的前置动作类型；每类背后接系统设置里的真实管理。"""

    START_SYSTEM = "start_system"            # 拉起被测系统（选一个系统版本/ref）
    START_EVAL_PROGRAM = "start_eval_program"  # 拉起评估程序（选一个评估代码版本/ref）
    CUSTOM_SCRIPT = "custom_script"          # 自定义脚本（seed/迁移/临时依赖），无版本


class Precondition(BaseModel):
    """task 的一条前置条件（有序执行）。

    版本(``ref``)在**运行时选定**——task 定义里可留空当"槽位"，跑的时候才填。
    """

    kind: PreconditionKind
    name: str | None = None                  # 人读标签 / helm release 名
    program_id: str | None = None            # 引用的 系统程序/评估程序 注册项（展示溯源用）
    git_url: str | None = None               # 固化：保存任务时从注册项复制
    path: str | None = None                  # 固化：仓库内单元目录（None = 根）
    branch: str | None = None                # 固化的分支名（用户可见）
    commit: str | None = None                # 固化的 commit sha（部署用它，钉死可复现）
    script: str | None = None                # custom_script 的脚本内容
    env: str | None = None                   # 固化：部署配置（.env.eval 内容，KEY=VALUE 每行）


class Task(BaseModel):
    """评估任务定义：数据集 + **有序前置条件** + 评估观测目标。

    运行一次 task = 一条运行记录(experiment)：前置条件把被测系统、评估程序按序拉起，
    再用数据集跑评估。前置条件包含：启动系统 / 启动评估程序 / 自定义脚本。
    """

    id: str = ""
    name: str
    system_id: str
    dataset_name: str | None = None
    preconditions: list[Precondition] = []
    dataset_id: str | None = None            # 选定的用例库；None = 不跑用例
    case_ids: list[str] | None = None        # 用例清单：None = 全部用例（动态跟随用例库）
    eval_target: str | None = None           # 评估观测的被测服务（如 quote）
