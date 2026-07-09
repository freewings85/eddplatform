"""API 层（真实数据，无占位 demo）：真实系统/版本/用例集、需求 CRUD、触发评估校验、
两评估→对比。评估执行本身打 k8s，这里只测端点契约与对比装配（用 store 直接种入已完成评估）。
"""
from fastapi.testclient import TestClient

from eddplatform.api.app import app
from eddplatform.api.store import STORE
from eddplatform.domain.models import (
    CaseResult,
    EvalResult,
    EvalStatus,
    Evaluation,
)

client = TestClient(app)


def test_systems_are_real_no_demo():
    ids = {s["id"] for s in client.get("/api/systems").json()}
    assert "chatagent" in ids
    assert not ({"insurance", "cs", "store", "reco"} & ids)   # 占位 demo 已清


def test_versions_are_2_0_and_2_3():
    labels = {v["label"] for v in client.get("/api/systems/chatagent/versions").json()}
    assert labels == {"2.0", "2.3"}


def test_dataset_has_real_cases():
    ds = client.get("/api/systems/chatagent/dataset").json()
    assert ds["system_id"] == "chatagent"
    assert len(ds["cases"]) == 15


def test_dataset_filter_unknown_requirement_returns_empty_not_error():
    r = client.get("/api/systems/chatagent/dataset", params={"requirement": "R-nope"})
    assert r.status_code == 200
    assert r.json()["cases"] == []


def test_requirement_create_then_list_and_detail():
    body = {"title": "多轮缓存命中率不回退", "external_key": "PROJ-9001"}
    created = client.post("/api/systems/chatagent/requirements", json=body).json()
    assert created["system_id"] == "chatagent" and created["id"].startswith("R-")

    listed = client.get("/api/systems/chatagent/requirements").json()
    assert created["id"] in {x["id"] for x in listed}

    filt = client.get("/api/systems/chatagent/requirements", params={"key": "PROJ-9001"}).json()
    assert [x["id"] for x in filt] == [created["id"]]

    detail = client.get(f"/api/requirements/{created['id']}").json()
    assert detail["external_key"] == "PROJ-9001"
    assert "status" not in detail                    # 薄追溯层：无状态


def test_evaluate_unknown_version_404():
    r = client.post("/api/systems/chatagent/evaluate", params={"version": "9.9"})
    assert r.status_code == 404


def _seed_eval(version, results):
    ev = Evaluation(id=STORE.next_eval_id(), name=f"chatagent {version}", system_id="chatagent",
                    version_label=version, dataset_name="ds", sandbox_config="k8s",
                    run_id=None, status=EvalStatus.COMPLETED,
                    result=EvalResult(pass_rate=sum(r[1] for r in results) / len(results),
                                      metrics={"维度-非缓存token": 100.0 if version == "2.0" else 60.0},
                                      case_results=[CaseResult(case_id=c, passed=p) for c, p in results]))
    STORE.add_evaluation(ev)
    return ev


def test_comparison_from_two_completed_evaluations():
    a = _seed_eval("2.0", [("g1", True), ("s1", False)])
    b = _seed_eval("2.3", [("g1", True), ("s1", True)])
    cmp = client.get("/api/comparison", params={"baseline": a.id, "candidate": b.id}).json()
    assert cmp["baseline_eval_id"] == a.id and cmp["candidate_eval_id"] == b.id
    assert cmp["improved"] == 1 and cmp["regressed"] == 0
    metrics = {m["metric"] for m in cmp["metrics"]}
    assert "通过率" in metrics and "维度-非缓存token" in metrics


def test_comparison_404_when_no_completed_evaluations_for_versions():
    # 用不存在的 eval id → 404
    r = client.get("/api/comparison", params={"baseline": "E-x", "candidate": "E-y"})
    assert r.status_code == 404
