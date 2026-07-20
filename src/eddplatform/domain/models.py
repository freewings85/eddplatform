"""EddPlatform 领域模型。

对象关系（与 prototype/ 和 docs/ 一致）::

    System        被评系统（注册表；约定式部署直接用 git 仓库）
    EvalProgram   评估程序（独立 git 仓；code = RunCase workflow 名/队列）
    Dataset ─< Case（有自身版本 + 适用系统版本）
    Task          评估任务 = 数据集 + 有序前置条件 + 评估程序
    RunRecord     一次 task 执行（Temporal workflow 的平台侧记录）─< CaseRunResult
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


# --------------------------------------------------------------------------- 枚举
class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EvaluatorKind(str, Enum):
    BUILTIN = "builtin"          # pydantic-evals 内置(EqualsExpected/HasMatchingSpan/...)
    CUSTOM_CODE = "custom_code"  # 自定义 Evaluator 子类
    LLM_JUDGE = "llm_judge"      # LLMJudge


class OutputType(str, Enum):
    """对应 pydantic-evals 返回值自动归类：bool→assertion, number→score, str→label。"""

    ASSERTION = "assertion"
    SCORE = "score"
    LABEL = "label"


class ContextField(str, Enum):
    """评估器可读的 EvaluatorContext 字段（"看输出的哪部分"）。"""

    OUTPUT = "output"
    EXPECTED_OUTPUT = "expected_output"
    INPUTS = "inputs"
    METADATA = "metadata"
    DURATION = "duration"
    SPAN_TREE = "span_tree"


class EvaluatorScope(str, Enum):
    DATASET = "dataset"
    CASE = "case"
    REPORT = "report"


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
    ``code`` 是它认领的 Temporal RunCase workflow 名 = task queue：平台逐用例
    分派 child workflow 时按 ``code`` 找到它。分支/commit 同样在任务里固化。
    """

    id: str = ""                      # 空 = store 落库时生成（EP-0001）
    system_id: str = ""
    name: str
    git_url: str
    path: str = "."                   # 仓库内单元目录（评估程序可与被评系统同仓不同目录）
    code: str                         # RunCase workflow 名 + task queue
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
    """用例对应的线上轨迹——**轻引用**。

    轨迹本体的存储与查看交给 Langfuse（内嵌引擎），平台侧只存指针。
    """

    ref: str                              # Langfuse trace id
    url: str | None = None                # 直达轨迹视图的链接（host + id 拼）
    note: str | None = None               # 这条轨迹的问题简述


class TagNode(BaseModel):
    """标签树节点（每系统一棵树）。case 用完整路径（如 ``业务/报价``）引用标签。"""

    id: str
    name: str                             # 单层名字，不含 "/"
    parent_id: str | None = None          # None = 根
    path: str = ""                        # 计算得到的完整路径（业务/报价）


class Case(BaseModel):
    """用例：有自身版本(编辑历史) + 适用系统版本(多版本通用/某版本专属)。"""

    id: str = ""                          # 空 = 由 store 落库时生成
    name: str
    description: str | None = None        # 用例意图/在测什么
    inputs: dict | str = ""
    expected_output: dict | str | None = None
    tags: list[str] = []                  # 数据集内分组/筛选
    metadata: dict = {}
    case_version: str = "v1"              # 用例自身编辑版本
    applicable_versions: list[str] = []   # 适用的系统版本；空 = 全部通用
    evaluator_names: list[str] = []
    trace: CaseTrace | None = None        # 一条 case 对应一条轨迹（轻引用）
    author: str | None = None
    enabled: bool = True
    created_at: datetime | None = None    # store 自动维护
    updated_at: datetime | None = None    # store 自动维护

    def applies_to(self, version_label: str) -> bool:
        return not self.applicable_versions or version_label in self.applicable_versions


class DatasetInfo(BaseModel):
    """用例库注册项：一个系统可有多个用例库，用例按库分区。"""

    id: str = ""                          # 空 = store 落库时生成（DS-0001）
    system_id: str = ""
    name: str
    description: str | None = None


class Dataset(BaseModel):
    name: str
    system_id: str
    cases: list[Case] = []
    evaluator_names: list[str] = []

    def cases_for_comparison(self, version_a: str, version_b: str) -> list[Case]:
        """只保留对两个版本都适用的用例——对比才公平。"""
        return [
            c for c in self.cases
            if c.enabled and c.applies_to(version_a) and c.applies_to(version_b)
        ]


# --------------------------------------------------------------------------- 评估器
class EvaluatorDef(BaseModel):
    """可管理的评估器定义。字段对齐 Pydantic Evals(执行) + Langfuse(管理)。

    见 docs/ 与项目记忆「评估器定义模型」。运行时由 evals.runner 映射为
    pydantic-evals 的 Evaluator / LLMJudge 执行。
    """

    name: str
    kind: EvaluatorKind
    builtin_type: str | None = None       # kind=builtin 时: EqualsExpected / HasMatchingSpan / ...
    input_field: ContextField = ContextField.OUTPUT
    json_path: str | None = None          # 读嵌套字段, 如 $.premium
    rule: str | None = None               # code 描述/表达式
    rubric: str | None = None             # LLMJudge 打分标准
    model: str | None = None              # 评委模型(仅 llm_judge)
    output_type: OutputType = OutputType.ASSERTION
    threshold: float | None = None        # 通过阈值(UI 层; pydantic-evals 原生无)
    scope: EvaluatorScope = EvaluatorScope.DATASET
    case_refs: list[str] = []             # 挂到哪些用例


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


class CaseResult(BaseModel):
    """（本地兜底评分器 engine.py 专用）单用例断言/分数汇总。"""

    case_id: str
    passed: bool
    assertions: dict[str, bool] = {}
    scores: dict[str, float] = {}
    labels: dict[str, str] = {}


class EvalResult(BaseModel):
    pass_rate: float
    metrics: dict[str, float] = {}
    case_results: list[CaseResult] = []


# --------------------------------------------------------------------------- 对比
class MetricDelta(BaseModel):
    metric: str
    baseline: float
    candidate: float

    @property
    def delta(self) -> float:
        return self.candidate - self.baseline


class Comparison(BaseModel):
    """两个评估结果的对比（先各自评估、再对比）。"""

    baseline_eval_id: str
    candidate_eval_id: str
    applicable_cases: int = 0             # 两版本都适用的用例数
    improved: int = 0
    regressed: int = 0
    unchanged: int = 0
    metrics: list[MetricDelta] = Field(default_factory=list)


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
