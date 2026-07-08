"""EddPlatform 领域模型。

对象关系（与 prototype/ 和 docs/ 一致）::

    System ─< Module(含 Git)
           ─< SystemVersion(钉住各模块 tag 的快照)
    SandboxConfig ── Environment(某版本的一次性实例)
    Dataset ─< Case(有自身版本 + 适用系统版本) ── EvaluatorDef
    RunRecord   一次执行: 日志/轨迹; 可单独运行或由评估产生
    Evaluation  = SystemVersion × Dataset × Environment → RunRecord + EvalResult
    Comparison  = 两个 EvalResult 的对比(只算两版本都适用的用例)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- 枚举
class IsolationLevel(str, Enum):
    NAMESPACE_NETPOL = "namespace+NetworkPolicy"  # 默认，最轻
    VCLUSTER = "vCluster"                          # 强隔离
    KATA_GVISOR = "Kata/gVisor"                    # 跑高危工具


class VersionStatus(str, Enum):
    DRAFT = "draft"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class RunType(str, Enum):
    STANDALONE = "standalone"    # 单独运行：拉起环境自测，不评分
    EVALUATION = "evaluation"    # 由评估产生


class RunStatus(str, Enum):
    PENDING = "pending"
    BUILDING = "building"
    RUNNING = "running"
    SCORING = "scoring"
    COMPLETED = "completed"
    FAILED = "failed"
    DESTROYED = "destroyed"


class EvalStatus(str, Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
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
    TTFT = "ttft"                 # 首 token 时延（信号类）
    USAGE = "usage"              # token usage（信号类）
    COST = "cost"                # 花费（信号类）


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
    modules: list[Module] = []
    prod_version: str | None = None


class SystemVersion(BaseModel):
    """一组模块钉住 tag/commit 的快照，如 v2 = 2 新 + 3 旧。"""

    id: str
    system_id: str
    label: str                        # v1 / v2
    module_pins: dict[str, str]       # module name -> tag/commit
    status: VersionStatus = VersionStatus.DRAFT
    note: str | None = None
    requirement_ids: list[str] = []   # 该版本交付哪些需求（追溯到 Requirement.id）


# --------------------------------------------------------------------------- 环境 / 沙箱
class SandboxConfig(BaseModel):
    """可复用可选择的沙箱配置；运行/评估时选一套拉起。"""

    name: str
    isolation: IsolationLevel = IsolationLevel.NAMESPACE_NETPOL
    cpu: int = 2
    mem_gb: int = 4
    ttl_hours: float = 2.0
    traffic_split: bool = False       # Istio v1/v2 流量切分


class Environment(BaseModel):
    """某系统版本的一次性(ephemeral)实例；跑完/到期销毁。"""

    id: str
    name: str
    config_name: str
    version_label: str
    status: RunStatus = RunStatus.PENDING
    ttl_hours_left: float | None = None
    purpose: str | None = None        # "评估 #R-1042" / "单独运行"


# --------------------------------------------------------------------------- 用例 / 用例集
class Case(BaseModel):
    """用例：有自身版本(编辑历史) + 适用系统版本(多版本通用/某版本专属)。"""

    id: str
    name: str
    inputs: dict | str
    expected_output: dict | str | None = None
    metadata: dict = {}
    case_version: str = "v1"
    applicable_versions: list[str] = []   # 空 = 全部版本通用
    evaluator_names: list[str] = []
    requirement_ids: list[str] = []        # 这条用例验收哪些需求（多对多标签）
    enabled: bool = True

    def applies_to(self, version_label: str) -> bool:
        return not self.applicable_versions or version_label in self.applicable_versions


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


# --------------------------------------------------------------------------- 需求（追溯锚点）
class Requirement(BaseModel):
    """薄追溯锚点：详情（描述/状态/流转）在 Jira（唯一真相源），平台只存刚够
    显示与挂接的字段。不带状态——状态以 Jira 为准。见 docs/superpowers/specs/。
    """

    id: str                               # 平台内部 id，如 R-101
    system_id: str
    title: str
    description: str | None = None        # 建时填，可用于推送到 Jira
    external_key: str | None = None       # Jira 号，如 PROJ-2043
    external_url: str | None = None       # 直接跳 Jira
    note: str | None = None


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
    dimension: str | None = None          # 维度分组(正确性/文字质量/轨迹/延迟/TTFT/成本), 仅 UI/报告用


# --------------------------------------------------------------------------- 运行 / 结果 / 评估
class RunRecord(BaseModel):
    """一次运行：拉起环境 → 跑，产出日志 + 轨迹。可脱离评估独立存在。"""

    id: str
    type: RunType
    system_id: str
    version_label: str
    environment_id: str | None = None
    status: RunStatus = RunStatus.PENDING
    started_at: datetime | None = None
    duration_s: float | None = None
    eval_id: str | None = None            # 关联评估；单独运行为 None
    trace_ref: str | None = None          # Langfuse trace 链接
    log: list[str] = []


class CaseResult(BaseModel):
    case_id: str
    passed: bool
    assertions: dict[str, bool] = {}
    scores: dict[str, float] = {}
    labels: dict[str, str] = {}


class EvalResult(BaseModel):
    pass_rate: float
    metrics: dict[str, float] = {}
    case_results: list[CaseResult] = []


class Evaluation(BaseModel):
    """一个评估任务 = 系统版本 × 用例集 × 环境；一定带一条运行记录。"""

    id: str
    name: str
    system_id: str
    version_label: str
    dataset_name: str
    sandbox_config: str
    run_id: str | None = None             # 必带一条运行记录
    status: EvalStatus = EvalStatus.DRAFT
    result: EvalResult | None = None


# --------------------------------------------------------------------------- 对比
class MetricDelta(BaseModel):
    metric: str
    baseline: float
    candidate: float

    @property
    def delta(self) -> float:
        return self.candidate - self.baseline


class RequirementRollup(BaseModel):
    """把用例级结果卷到需求级：达标=验收用例在该版本全部通过（只算两版共有用例）。"""

    requirement_id: str
    title: str
    external_key: str | None = None
    total_cases: int                      # 两版都适用的验收用例数
    baseline_passed: int
    candidate_passed: int

    @property
    def baseline_met(self) -> bool:
        return self.total_cases > 0 and self.baseline_passed == self.total_cases

    @property
    def candidate_met(self) -> bool:
        return self.total_cases > 0 and self.candidate_passed == self.total_cases

    @property
    def verdict(self) -> str:
        if self.candidate_met and not self.baseline_met:
            return "达标"                  # 未达 → 达
        if self.baseline_met and not self.candidate_met:
            return "回归"                  # 达 → 未达
        if self.baseline_met and self.candidate_met:
            return "保持"
        return "仍未达标"


class Comparison(BaseModel):
    """两个评估结果的对比（先各自评估、再对比）。"""

    baseline_eval_id: str
    candidate_eval_id: str
    applicable_cases: int = 0             # 两版本都适用的用例数
    improved: int = 0
    regressed: int = 0
    unchanged: int = 0
    metrics: list[MetricDelta] = Field(default_factory=list)
    by_requirement: list[RequirementRollup] = Field(default_factory=list)
