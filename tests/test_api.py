"""API 层：需求列表/详情/新建、用例按需求过滤、对比带需求汇总。"""

from fastapi.testclient import TestClient

from eddplatform.api.app import app

client = TestClient(app)


def test_list_requirements():
    r = client.get("/api/systems/insurance/requirements")
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()}
    assert {"R-101", "R-102", "R-103"} <= ids


def test_filter_requirements_by_jira_key():
    r = client.get("/api/systems/insurance/requirements", params={"key": "PROJ-2043"})
    assert [x["id"] for x in r.json()] == ["R-101"]


def test_get_requirement_detail():
    r = client.get("/api/requirements/R-101")
    assert r.status_code == 200
    assert r.json()["external_key"] == "PROJ-2043"
    assert "status" not in r.json()          # 薄追溯层：无状态


def test_create_requirement_without_jira():
    body = {"title": "新需求·车险扩项", "external_key": "PROJ-9000"}
    r = client.post("/api/systems/insurance/requirements", json=body)
    assert r.status_code == 200
    j = r.json()
    assert j["system_id"] == "insurance"
    assert j["external_key"] == "PROJ-9000"
    assert j["id"].startswith("R-")


def test_dataset_filter_by_requirement():
    r = client.get("/api/systems/insurance/dataset", params={"requirement": "R-101"})
    ids = {c["id"] for c in r.json()["cases"]}
    assert ids == {"17", "88", "102"}


def test_comparison_includes_by_requirement():
    body = client.get("/api/comparison").json()
    assert "by_requirement" in body
    r101 = next(x for x in body["by_requirement"] if x["requirement_id"] == "R-101")
    assert r101["candidate_passed"] == r101["total_cases"]   # v2 达标
