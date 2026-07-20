"""评估程序 CRUD：code（RunCase workflow 名/队列）是核心字段。"""
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


def test_eval_program_crud(client):
    r = client.post("/api/systems/sys1/eval-programs", json={
        "name": "chatagent 评估", "git_url": "/mnt/repos/chatagent-eval",
        "path": "edd/eval"})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert pid.startswith("EP-")
    assert client.get("/api/systems/sys1/eval-programs").json()[0]["path"] == "edd/eval"
    r = client.put(f"/api/systems/sys1/eval-programs/{pid}", json={
        "name": "chatagent 评估", "git_url": "/mnt/repos/chatagent-eval",
        "path": "edd/eval2"})
    assert r.json()["path"] == "edd/eval2"
    assert client.delete(f"/api/systems/sys1/eval-programs/{pid}").status_code == 204
    assert client.get("/api/systems/sys1/eval-programs").json() == []


def test_git_url_with_whitespace_rejected(client):
    """粘贴了「名称 + 编号 + 地址」整格文本时直接拒绝，不能落库。"""
    r = client.post("/api/systems/sys1/eval-programs", json={
        "name": "坏地址", "git_url": "mainagent SP-0001\tssh://git@x/y.git"})
    assert r.status_code == 422
