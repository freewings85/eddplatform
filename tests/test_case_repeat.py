"""每用例执行次数：多次尝试聚合语义（aggregate_attempts）。"""
from eddplatform.runtime.temporal.shared import CaseResultOut, aggregate_attempts


def _r(status: str, *, scores=None, metrics=None, detail="", report="") -> CaseResultOut:
    return CaseResultOut(case_id="c1", status=status, scores=scores or {},
                         metrics=metrics or {}, detail=detail, report=report)


def test_single_attempt_passthrough():
    agg = aggregate_attempts("c1", [_r("failed", detail="断言未过")])
    assert agg.status == "failed" and agg.attempts == 1 and agg.passed_attempts == 0
    assert "pass_rate" not in agg.scores  # 单次不引入聚合分数


def test_all_passed():
    agg = aggregate_attempts("c1", [_r("passed"), _r("passed"), _r("passed")])
    assert agg.status == "passed"
    assert agg.attempts == 3 and agg.passed_attempts == 3
    assert agg.scores["pass_rate"] == 1.0


def test_flaky_marks_failed_with_pass_rate():
    agg = aggregate_attempts("c1", [
        _r("passed"), _r("failed", detail="第二次没调工具"), _r("passed")])
    assert agg.status == "failed"          # 全过才算过
    assert agg.passed_attempts == 2 and agg.attempts == 3
    assert agg.scores["pass_rate"] == 0.67
    assert "2/3 次通过" in agg.detail and "第2次" in agg.detail


def test_error_only_when_no_failed():
    assert aggregate_attempts("c1", [_r("passed"), _r("error")]).status == "error"
    assert aggregate_attempts("c1", [_r("error"), _r("failed")]).status == "failed"
    assert aggregate_attempts("c1", [_r("skipped"), _r("skipped")]).status == "skipped"


def test_metrics_averaged_reports_joined():
    agg = aggregate_attempts("c1", [
        _r("passed", metrics={"task_duration_s": 2.0}, report="r1"),
        _r("passed", metrics={"task_duration_s": 4.0}, report="r2"),
    ])
    assert agg.metrics["task_duration_s"] == 3.0
    assert "第 1/2 次" in agg.report and "r2" in agg.report
