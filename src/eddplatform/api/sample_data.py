"""示例数据：保险报价系统 v1/v2（与 prototype/ 一致），用于点亮 API 骨架。

真实实现里这些应来自 DB + Harbor + Langfuse；此处仅为可运行的占位。
"""

from __future__ import annotations

from eddplatform.domain.models import (
    Case,
    Comparison,
    ContextField,
    Dataset,
    Environment,
    EvalResult,
    EvalStatus,
    Evaluation,
    EvaluatorDef,
    EvaluatorKind,
    IsolationLevel,
    MetricDelta,
    Module,
    OutputType,
    RunRecord,
    RunStatus,
    RunType,
    SandboxConfig,
    System,
    SystemVersion,
    VersionStatus,
)

# --- 系统与模块 ------------------------------------------------------------
INSURANCE_MODULES = [
    Module(name="intent-service", git_url="git@git.co/insur/intent.git",
           image="registry/intent", prod_tag="1.4.2", owner="李雷"),
    Module(name="quote-engine", git_url="git@git.co/insur/quote.git", branch="release/2.2",
           image="registry/quote", prod_tag="2.1.0", owner="张三"),
    Module(name="dialog-agent", git_url="git@git.co/insur/dialog.git",
           image="registry/dialog", prod_tag="0.9.5", owner="李四"),
    Module(name="store-service", git_url="git@git.co/insur/store.git",
           image="registry/store", prod_tag="3.0.1", owner="王五"),
    Module(name="memory-service", git_url="git@git.co/insur/memory.git",
           image="registry/memory", prod_tag="1.2.0", owner="赵六"),
]

SYSTEMS = [
    System(id="insurance", name="保险报价系统", owner="李雷",
           modules=INSURANCE_MODULES, prod_version="v1"),
    System(id="cs", name="智能客服系统", owner="韩梅", prod_version="v4"),
    System(id="store", name="门店服务系统", owner="王强", prod_version="v2"),
    System(id="reco", name="项目推荐系统", owner="刘敏", prod_version="v3"),
]

VERSIONS = [
    SystemVersion(id="insurance-v1", system_id="insurance", label="v1",
                  module_pins={"intent-service": "1.4.2", "quote-engine": "2.1.0",
                               "dialog-agent": "0.9.5", "store-service": "3.0.1",
                               "memory-service": "1.2.0"},
                  status=VersionStatus.PRODUCTION),
    SystemVersion(id="insurance-v2", system_id="insurance", label="v2",
                  module_pins={"intent-service": "1.4.2", "quote-engine": "2.2.0",
                               "dialog-agent": "1.0.0", "store-service": "3.0.1",
                               "memory-service": "1.2.0"},
                  status=VersionStatus.DRAFT, note="保险报价重构：2 新 + 3 旧"),
]

# --- 沙箱配置与运行中实例 --------------------------------------------------
SANDBOX_CONFIGS = [
    SandboxConfig(name="默认-轻量", isolation=IsolationLevel.NAMESPACE_NETPOL, cpu=2, mem_gb=4),
    SandboxConfig(name="强隔离", isolation=IsolationLevel.VCLUSTER, cpu=4, mem_gb=8, traffic_split=True),
    SandboxConfig(name="高危工具", isolation=IsolationLevel.KATA_GVISOR, cpu=2, mem_gb=4, ttl_hours=1.0),
]

ENVIRONMENTS = [
    Environment(id="release-insur-v1", name="release-insur-v1", config_name="默认-轻量",
                version_label="v1", status=RunStatus.RUNNING, ttl_hours_left=1.97, purpose="评估 #R-1041"),
    Environment(id="release-insur-v2", name="release-insur-v2", config_name="默认-轻量",
                version_label="v2", status=RunStatus.RUNNING, ttl_hours_left=1.97, purpose="评估 #R-1042"),
    Environment(id="dev-sandbox-a", name="dev-sandbox-a", config_name="强隔离",
                version_label="v2", status=RunStatus.RUNNING, ttl_hours_left=0.70, purpose="单独运行 #R-1050"),
]

# --- 用例集（用例有版本 + 适用系统版本）-----------------------------------
DATASET = Dataset(
    name="保险报价", system_id="insurance",
    evaluator_names=["金额校验", "条款解释", "工具调用正确", "延迟阈值", "提示词注入检测"],
    cases=[
        Case(id="17", name="新能源车型报价", inputs="新能源车报价请求",
             expected_output={"premium": 4260}, case_version="v3",
             applicable_versions=["v1", "v2", "v3"], evaluator_names=["金额校验", "工具调用正确"]),
        Case(id="63", name="多车型比价", inputs="三款车型比价", case_version="v2",
             applicable_versions=["v1", "v2"], evaluator_names=["条款解释"]),
        Case(id="88", name="含优惠叠加报价", inputs="优惠叠加", expected_output={"premium": 3100},
             case_version="v1", applicable_versions=[], evaluator_names=["金额校验"]),
        Case(id="91", name="历史出险影响保费", inputs="有出险记录", case_version="v4",
             applicable_versions=["v1", "v2"], evaluator_names=["金额校验", "延迟阈值"]),
        Case(id="102", name="新能源专属补贴校验", inputs="补贴校验", case_version="v1",
             applicable_versions=["v2"], evaluator_names=["金额校验"]),  # 仅 v2 专属
    ],
)

# --- 评估器定义（对齐 Pydantic Evals / Langfuse）--------------------------
EVALUATORS = [
    EvaluatorDef(name="金额校验", kind=EvaluatorKind.CUSTOM_CODE, input_field=ContextField.OUTPUT,
                 json_path="$.premium", rule="output.premium == expected.premium",
                 output_type=OutputType.ASSERTION, case_refs=["17", "88", "91"]),
    EvaluatorDef(name="条款解释", kind=EvaluatorKind.LLM_JUDGE, input_field=ContextField.OUTPUT,
                 rubric="只依据真实条款，不得编造优惠/减免；1=严重编造，5=完全准确",
                 model="openai:gpt-5.2", output_type=OutputType.SCORE, threshold=4.0, case_refs=["63"]),
    EvaluatorDef(name="工具调用正确", kind=EvaluatorKind.BUILTIN, builtin_type="HasMatchingSpan",
                 input_field=ContextField.SPAN_TREE, output_type=OutputType.ASSERTION, case_refs=["17"]),
    EvaluatorDef(name="延迟阈值", kind=EvaluatorKind.BUILTIN, builtin_type="MaxDuration",
                 input_field=ContextField.DURATION, output_type=OutputType.ASSERTION,
                 threshold=3.0, case_refs=["91"]),
    EvaluatorDef(name="提示词注入检测", kind=EvaluatorKind.CUSTOM_CODE, input_field=ContextField.OUTPUT,
                 rule="未越权 / 未泄露", output_type=OutputType.ASSERTION),
]

# --- 运行记录（单独运行 / 评估运行）---------------------------------------
RUNS = [
    RunRecord(id="R-1042", type=RunType.EVALUATION, system_id="insurance", version_label="v2",
              environment_id="release-insur-v2", status=RunStatus.COMPLETED, duration_s=360,
              eval_id="E-2001", trace_ref="langfuse://trace/R-1042"),
    RunRecord(id="R-1041", type=RunType.EVALUATION, system_id="insurance", version_label="v1",
              environment_id="release-insur-v1", status=RunStatus.COMPLETED, duration_s=300,
              eval_id="E-2000", trace_ref="langfuse://trace/R-1041"),
    RunRecord(id="R-1050", type=RunType.STANDALONE, system_id="insurance", version_label="v2",
              environment_id="dev-sandbox-a", status=RunStatus.RUNNING),
    RunRecord(id="R-1039", type=RunType.STANDALONE, system_id="insurance", version_label="v1",
              status=RunStatus.COMPLETED, duration_s=480),
]

# --- 评估任务与结果 --------------------------------------------------------
EVALUATIONS = [
    Evaluation(id="E-2000", name="保险报价重构·基线", system_id="insurance", version_label="v1",
               dataset_name="保险报价", sandbox_config="默认-轻量", run_id="R-1041",
               status=EvalStatus.COMPLETED, result=EvalResult(pass_rate=0.82, metrics={"judge": 3.9})),
    Evaluation(id="E-2001", name="保险报价重构·候选", system_id="insurance", version_label="v2",
               dataset_name="保险报价", sandbox_config="默认-轻量", run_id="R-1042",
               status=EvalStatus.COMPLETED, result=EvalResult(pass_rate=0.86, metrics={"judge": 4.2})),
]

COMPARISON = Comparison(
    baseline_eval_id="E-2000", candidate_eval_id="E-2001",
    applicable_cases=178, improved=22, regressed=8, unchanged=148,
    metrics=[
        MetricDelta(metric="通过率", baseline=0.82, candidate=0.86),
        MetricDelta(metric="结果质量(judge)", baseline=3.9, candidate=4.2),
        MetricDelta(metric="工具调用正确率", baseline=0.91, candidate=0.95),
        MetricDelta(metric="P95延迟(s)", baseline=2.1, candidate=2.6),
        MetricDelta(metric="成本/用例(元)", baseline=0.011, candidate=0.013),
    ],
)


def system_by_id(sid: str) -> System | None:
    return next((s for s in SYSTEMS if s.id == sid), None)
