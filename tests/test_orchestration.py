"""发布评估编排（框架无关核心）：渲染 manifest → 一次性环境 → 跑 → 评 → 对比 → 销。

全程离线：MockProvider（无 k8s）+ 进程内 target + 本地兜底评分器。
"""

from eddplatform.domain.models import (
    Case,
    Dataset,
    Module,
    Requirement,
    RunStatus,
    SystemVersion,
)
from eddplatform.evals.engine import EqualsExpected
from eddplatform.orchestration.manifest import render_manifest
from eddplatform.orchestration.pipeline import run_release_evaluation
from eddplatform.orchestration.providers import MockProvider

MODULES = [
    Module(name="quote-engine", git_url="g", image="registry/quote"),
    Module(name="dialog-agent", git_url="g", image="registry/dialog"),
]
V1 = SystemVersion(id="v1", system_id="ins", label="v1",
                   module_pins={"quote-engine": "2.1.0", "dialog-agent": "0.9.5"})
V2 = SystemVersion(id="v2", system_id="ins", label="v2",
                   module_pins={"quote-engine": "2.2.0", "dialog-agent": "1.0.0"},
                   requirement_ids=["R-101"])

DATASET = Dataset(name="保险报价", system_id="ins", cases=[
    Case(id="17", name="ev", inputs={"car": "ev"}, expected_output={"premium": 4260},
         evaluator_names=["金额校验"], requirement_ids=["R-101"]),
    Case(id="88", name="promo", inputs={"car": "petrol"}, expected_output={"premium": 3100},
         evaluator_names=["金额校验"], requirement_ids=["R-101"]),
    Case(id="91", name="claims", inputs={"car": "ev", "claims": 2}, expected_output={"premium": 5200},
         evaluator_names=["金额校验"], requirement_ids=["R-103"]),
    Case(id="102", name="v2only", inputs={"car": "ev"}, expected_output={"premium": 4260},
         applicable_versions=["v2"], evaluator_names=["金额校验"], requirement_ids=["R-101"]),
])
EVALUATORS = {"金额校验": EqualsExpected(name="金额校验", path="$.premium")}
REQUIREMENTS = [
    Requirement(id="R-101", system_id="ins", title="新能源报价修复", external_key="PROJ-2043"),
    Requirement(id="R-103", system_id="ins", title="出险延迟", external_key="PROJ-2051"),
]


def _v1(inputs):
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 3820}                    # #17 bug
    return {"premium": 5200 if inputs.get("claims") else 3100}


def _v2(inputs):
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 4260}                    # fixed
    return {"premium": 5200 if inputs.get("claims") else 3100}


def _factory(label, manifest, env_id):
    return _v1 if label == "v1" else _v2


# --- Harbor：渲染系统版本 manifest ----------------------------------------
def test_render_manifest_pins_image_and_tag():
    m = render_manifest(MODULES, V2)
    svc = {s["name"]: s["image"] for s in m["services"]}
    assert svc["quote-engine"] == "registry/quote:2.2.0"
    assert svc["dialog-agent"] == "registry/dialog:1.0.0"
    assert m["version"] == "v2" and len(m["services"]) == 2


# --- MockProvider：一次性环境生命周期 -------------------------------------
def test_mock_provider_lifecycle():
    p = MockProvider()
    eid = p.create({"services": []}, ttl_hours=2.0)
    assert p.status(eid) == RunStatus.RUNNING
    p.destroy(eid)
    assert p.status(eid) == RunStatus.DESTROYED
    assert p.live_count() == 0


# --- 端到端编排：建→跑→评→对比→销 ---------------------------------------
def test_release_evaluation_end_to_end():
    p = MockProvider()
    res = run_release_evaluation(
        modules=MODULES, baseline_version=V1, candidate_version=V2,
        dataset=DATASET, evaluators=EVALUATORS, target_factory=_factory,
        provider=p, requirements=REQUIREMENTS,
    )
    # #17 修复 → 改善 1、回归 0
    assert res.comparison.improved == 1
    assert res.comparison.regressed == 0
    # 只统计两版共有用例（#102 仅 v2 → 不计入对比）
    assert res.comparison.applicable_cases == 3
    # 需求汇总：R-101 未达→达
    r101 = next(r for r in res.comparison.by_requirement if r.requirement_id == "R-101")
    assert r101.baseline_passed == 1 and r101.candidate_passed == 2


def test_release_evaluation_destroys_all_environments():
    """ephemeral：跑完两个版本的环境都必须销毁。"""
    p = MockProvider()
    run_release_evaluation(
        modules=MODULES, baseline_version=V1, candidate_version=V2,
        dataset=DATASET, evaluators=EVALUATORS, target_factory=_factory, provider=p,
    )
    assert p.live_count() == 0
