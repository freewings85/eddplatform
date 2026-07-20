"""系统注册 CRUD（真 MySQL 测试库 + TestClient）。"""
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
    return TestClient(app_module.app)


def test_systems_empty_initially(client):
    assert client.get("/api/systems").json() == []


def test_create_get_update_delete_system(client):
    r = client.post("/api/systems", json={"id": "chatagent", "name": "chatagent 2.3"})
    assert r.status_code == 201
    assert client.get("/api/systems/chatagent").json()["name"] == "chatagent 2.3"
    r = client.post("/api/systems", json={"id": "chatagent", "name": "重复"})
    assert r.status_code == 409
    r = client.put("/api/systems/chatagent", json={"id": "chatagent", "name": "改名", "owner": "leo"})
    assert r.json()["owner"] == "leo"
    assert client.delete("/api/systems/chatagent").status_code == 204
    assert client.get("/api/systems/chatagent").status_code == 404


def test_delete_system_with_tasks_conflicts(client):
    client.post("/api/systems", json={"id": "s1", "name": "系统1"})
    client.post("/api/systems/s1/tasks", json={"name": "t", "system_id": "s1"})
    assert client.delete("/api/systems/s1").status_code == 409


def test_system_program_crud(client):
    """系统程序注册：名称 + git 地址（+目录），建任务时下拉复用。"""
    client.post("/api/systems", json={"id": "s1", "name": "系统1"})
    r = client.post("/api/systems/s1/system-programs", json={
        "name": "mainagent", "git_url": "/repos/chatagent", "path": "edd/mainagent"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert pid.startswith("SP-")
    got = client.get("/api/systems/s1/system-programs").json()
    assert got[0]["name"] == "mainagent" and got[0]["path"] == "edd/mainagent"
    assert client.delete(f"/api/systems/s1/system-programs/{pid}").status_code == 204
    assert client.get("/api/systems/s1/system-programs").json() == []
