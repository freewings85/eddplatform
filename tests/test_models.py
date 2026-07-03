"""领域模型的核心不变量测试。"""

from eddplatform.api import sample_data as sd
from eddplatform.domain.models import Case, Comparison, MetricDelta


def test_case_applies_to_specific_version():
    only_v2 = Case(id="102", name="新能源专属补贴校验", inputs="x", applicable_versions=["v2"])
    assert only_v2.applies_to("v2")
    assert not only_v2.applies_to("v1")


def test_case_empty_applicable_means_all_versions():
    universal = Case(id="88", name="含优惠叠加", inputs="x", applicable_versions=[])
    assert universal.applies_to("v1")
    assert universal.applies_to("v99")


def test_comparison_only_counts_cases_applicable_to_both():
    """对比只统计两版本都适用的用例——#102(仅 v2) 必须被排除。"""
    shared = sd.DATASET.cases_for_comparison("v1", "v2")
    ids = {c.id for c in shared}
    assert "102" not in ids            # v2 专属，v1 不适用
    assert {"17", "63", "88", "91"} <= ids


def test_metric_delta():
    d = MetricDelta(metric="通过率", baseline=0.82, candidate=0.86)
    assert round(d.delta, 2) == 0.04


def test_evaluation_always_has_a_run():
    """评估任务一定带一条运行记录。"""
    for e in sd.EVALUATIONS:
        assert e.run_id is not None


def test_comparison_model_roundtrip():
    c = sd.COMPARISON
    assert isinstance(c, Comparison)
    assert c.applicable_cases == 178
    assert c.improved + c.regressed + c.unchanged == 178
