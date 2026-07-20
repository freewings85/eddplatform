"""评估任务 CRUD：持久化 + 系统存在性校验。"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(test_db, monkeypatch):
    import eddplatform.api.app as app_module
    from eddplatform.store import (CaseStore, DatasetStore, EvalProgramStore, RunStore,
                                   SystemStore, TagStore, TaskStore)
    monkeypatch.setattr(app_module, "store", CaseStore(db=test_db))
    monkeypatch.setattr(app_module, "tag_store", TagStore(db=test_db))
    from eddplatform.store import DatasetStore
    monkeypatch.setattr(app_module, "dataset_store", DatasetStore(db=test_db))
    monkeypatch.setattr(app_module, "system_store", SystemStore(db=test_db))
    monkeypatch.setattr(app_module, "task_store", TaskStore(db=test_db))
    monkeypatch.setattr(app_module, "eval_program_store", EvalProgramStore(db=test_db))
    monkeypatch.setattr(app_module, "run_store", RunStore(db=test_db))
    c = TestClient(app_module.app)
    c.post("/api/systems", json={"id": "sys1", "name": "系统1"})
    return c


def test_task_requires_existing_system(client):
    r = client.post("/api/systems/nope/tasks", json={"name": "t", "system_id": "nope"})
    assert r.status_code == 404


def test_task_case_ids_roundtrip(client):
    """用例清单：空/None = 全部用例（动态），列表 = 固定勾选。"""
    r = client.post("/api/systems/sys1/tasks", json={
        "name": "选例任务", "system_id": "sys1", "case_ids": ["c1", "c3"],
        "preconditions": [{"kind": "start_system", "git_url": "/repo", "branch": "2.3-eval", "commit": "abc123def"}]})
    assert r.status_code == 201
    tid = r.json()["id"]
    got = client.get("/api/systems/sys1/tasks").json()
    assert got[0]["case_ids"] == ["c1", "c3"]
    r = client.put(f"/api/systems/sys1/tasks/{tid}",
                   json={"name": "选例任务", "system_id": "sys1", "case_ids": None})
    assert r.json()["case_ids"] is None


def test_task_crud_persists(client, test_db):
    r = client.post("/api/systems/sys1/tasks", json={
        "name": "guide 冒烟", "system_id": "sys1",
        "preconditions": [{"kind": "start_system", "git_url": "/repo", "branch": "2.3-eval", "commit": "abc123def"}]})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert tid.startswith("T-")
    from eddplatform.store import TaskStore
    assert TaskStore(db=test_db).get("sys1", tid).name == "guide 冒烟"
    r = client.put(f"/api/systems/sys1/tasks/{tid}",
                   json={"name": "改名", "system_id": "sys1"})
    assert r.json()["name"] == "改名"
    assert client.delete(f"/api/systems/sys1/tasks/{tid}").status_code == 204
    assert client.get("/api/systems/sys1/tasks").json() == []
