"""领域模型的核心不变量测试。"""

from eddplatform.domain.models import (
    Case,
    Dataset,
    EvalProgram,
    MetricDelta,
    RunRecord,
    RunStatus,
)


def test_case_applies_to_specific_version():
    only_v2 = Case(id="102", name="新能源专属补贴校验", inputs="x", applicable_versions=["v2"])
    assert only_v2.applies_to("v2")
    assert not only_v2.applies_to("v1")


def test_case_empty_applicable_means_all_versions():
    universal = Case(id="88", name="含优惠叠加", inputs="x", applicable_versions=[])
    assert universal.applies_to("v1")
    assert universal.applies_to("v99")


def test_comparison_only_counts_cases_applicable_to_both():
    """对比只统计两版本都适用的用例——仅 v2 适用的必须被排除。"""
    ds = Dataset(name="d", system_id="s", cases=[
        Case(id="1", name="通用", inputs="x"),
        Case(id="2", name="v2 专属", inputs="x", applicable_versions=["v2"]),
        Case(id="3", name="禁用", inputs="x", enabled=False),
    ])
    ids = {c.id for c in ds.cases_for_comparison("v1", "v2")}
    assert ids == {"1"}


def test_metric_delta():
    d = MetricDelta(metric="通过率", baseline=0.82, candidate=0.86)
    assert round(d.delta, 2) == 0.04


def test_eval_program_has_code_and_path():
    ep = EvalProgram(id="ep1", system_id="s", name="评估程序", git_url="/repo", code="chatagent-eval")
    assert ep.path == "." and ep.code == "chatagent-eval"


def test_run_record_shape():
    r = RunRecord(system_id="s", task_id="t")
    assert r.status == RunStatus.RUNNING and r.outcomes == []
