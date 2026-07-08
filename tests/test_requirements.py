"""需求追溯测试：Requirement 锚点 + 用例/版本标签 + 需求级对比汇总（rollup）。"""

from eddplatform.domain.models import (
    Case,
    CaseResult,
    Comparison,
    EvalResult,
    Requirement,
    SystemVersion,
)
from eddplatform.evals.engine import rollup_by_requirement


# --- 模型：Requirement 锚点 + requirement_ids 标签 -------------------------
def test_requirement_anchor_has_no_status_and_links_jira():
    """薄追溯层：需求不带状态，详情靠 external_key 引用 Jira。"""
    r = Requirement(id="R-101", system_id="insurance", title="新能源车型报价修复",
                    external_key="PROJ-2043", external_url="https://jira/PROJ-2043")
    assert not hasattr(r, "status")
    assert r.external_key == "PROJ-2043"


def test_case_and_version_carry_requirement_tags():
    c = Case(id="17", name="新能源车型报价", inputs="x", requirement_ids=["R-101"])
    v = SystemVersion(id="insurance-v2", system_id="insurance", label="v2",
                      module_pins={}, requirement_ids=["R-101", "R-102"])
    assert c.requirement_ids == ["R-101"]
    assert "R-102" in v.requirement_ids


# --- 需求级对比汇总 --------------------------------------------------------
CASES = [
    Case(id="17", name="新能源车型报价", inputs="x", requirement_ids=["R-101"]),
    Case(id="88", name="含优惠叠加报价", inputs="x", requirement_ids=["R-101"]),
    Case(id="63", name="多车型比价", inputs="x", requirement_ids=["R-102"]),
    Case(id="91", name="历史出险影响保费", inputs="x", requirement_ids=["R-103"]),
    Case(id="102", name="新能源专属补贴校验", inputs="x",
         applicable_versions=["v2"], requirement_ids=["R-101"]),  # 仅 v2 专属
]
REQUIREMENTS = [
    Requirement(id="R-101", system_id="insurance", title="新能源车型报价修复", external_key="PROJ-2043"),
    Requirement(id="R-102", system_id="insurance", title="条款解释防幻觉", external_key="PROJ-2044"),
    Requirement(id="R-103", system_id="insurance", title="保费计算延迟优化", external_key="PROJ-2051"),
]


def _result(passed: dict[str, bool]) -> EvalResult:
    crs = [CaseResult(case_id=k, passed=v) for k, v in passed.items()]
    rate = sum(passed.values()) / (len(passed) or 1)
    return EvalResult(pass_rate=rate, case_results=crs)


# v1 基线：17 挂了、其余过；102 未在 v1 跑（v2 专属）
BASELINE = _result({"17": False, "88": True, "63": True, "91": True})
# v2 候选：17 修好、63 幻觉回归、91 延迟回归；102 v2 专属过
CANDIDATE = _result({"17": True, "88": True, "63": False, "91": False, "102": True})


def test_rollup_reaches_each_requirement_with_common_cases():
    rollups = {r.requirement_id: r for r in
               rollup_by_requirement(BASELINE, CANDIDATE, CASES, REQUIREMENTS)}
    assert set(rollups) == {"R-101", "R-102", "R-103"}


def test_rollup_all_pass_semantics_and_excludes_non_common_cases():
    """达标=验收用例全过；#102 仅 v2 适用（非共有）→ 不计入 R-101。"""
    r101 = next(r for r in rollup_by_requirement(BASELINE, CANDIDATE, CASES, REQUIREMENTS)
                if r.requirement_id == "R-101")
    assert r101.total_cases == 2          # 17、88；102 被排除
    assert r101.baseline_passed == 1      # v1 只有 88 过
    assert r101.candidate_passed == 2     # v2 两条都过
    assert r101.baseline_met is False     # 全过才算达标
    assert r101.candidate_met is True


def test_rollup_verdicts_improved_and_regressed():
    rollups = {r.requirement_id: r for r in
               rollup_by_requirement(BASELINE, CANDIDATE, CASES, REQUIREMENTS)}
    assert rollups["R-101"].verdict == "达标"   # 未达 → 达
    assert rollups["R-102"].verdict == "回归"   # 达 → 未达
    assert rollups["R-103"].verdict == "回归"


def test_comparison_can_carry_by_requirement():
    c = Comparison(baseline_eval_id="A", candidate_eval_id="B",
                   by_requirement=rollup_by_requirement(BASELINE, CANDIDATE, CASES, REQUIREMENTS))
    assert len(c.by_requirement) == 3
