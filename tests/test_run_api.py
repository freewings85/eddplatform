"""执行触发 API：503 路径 + 异步 start + 后台回写。Temporal 用假 client 打桩。"""
import time

import pytest
from fastapi.testclient import TestClient

from eddplatform.runtime.temporal.shared import OutcomeOut, RunTaskOutput


class FakeHandle:
    def __init__(self, out):
        self._out = out

    async def result(self):
        if isinstance(self._out, Exception):
            raise self._out
        return self._out


class FakeClient:
    def __init__(self, out):
        self.out = out
        self.started = []

    async def start_workflow(self, wf, arg, *, id, task_queue, execution_timeout=None):
        self.started.append((id, task_queue, arg))
        return FakeHandle(self.out)


@pytest.fixture()
def client(test_db, monkeypatch):
    import eddplatform.api.app as app_module
    from eddplatform.store import (CaseStore, EvalProgramStore, RunStore,
                                   SystemStore, TagStore, TaskStore)
    for attr, obj in [("store", CaseStore(db=test_db)), ("tag_store", TagStore(db=test_db)),
                      ("system_store", SystemStore(db=test_db)),
                      ("task_store", TaskStore(db=test_db)),
                      ("eval_program_store", EvalProgramStore(db=test_db)),
                      ("run_store", RunStore(db=test_db))]:
        monkeypatch.setattr(app_module, attr, obj)
    c = TestClient(app_module.app)
    c.post("/api/systems", json={"id": "sys1", "name": "系统1"})
    c.post("/api/systems/sys1/tasks", json={
        "name": "冒烟", "system_id": "sys1",
        "preconditions": [{"kind": "start_system", "git_url": "/repo", "ref": "2.3-eval"}]})
    return c


def test_run_returns_503_when_temporal_down(client, monkeypatch):
    import eddplatform.api.run_service as rs

    async def no_client(_addr):
        raise OSError("connect refused")
    monkeypatch.setattr(rs, "_connect", no_client)
    r = client.post("/api/systems/sys1/tasks/T-0001/run")
    assert r.status_code == 503
    assert "Temporal server 未启动" in r.json()["detail"]
    assert client.get("/api/runs").json() == []


def test_run_starts_workflow_and_watch_writes_back(client, monkeypatch):
    import eddplatform.api.run_service as rs
    out = RunTaskOutput(namespace="ns", status="up", versions={"system": "abc"},
                        outcomes=[OutcomeOut("start_system", "sys", "ok", ref="abc")])
    fake = FakeClient(out)

    async def fake_connect(_addr):
        return fake
    monkeypatch.setattr(rs, "_connect", fake_connect)
    r = client.post("/api/systems/sys1/tasks/T-0001/run")
    assert r.status_code == 202
    run_id = r.json()["id"]
    assert fake.started and fake.started[0][0] == f"edd-run-{run_id}"
    got = None
    for _ in range(50):
        got = client.get(f"/api/runs/{run_id}").json()
        if got["status"] != "running":
            break
        time.sleep(0.1)
    assert got["status"] == "succeeded"
    assert got["versions"] == {"system": "abc"}
    assert got["outcomes"][0]["status"] == "ok"


def test_run_failure_writes_failed(client, monkeypatch):
    import eddplatform.api.run_service as rs
    fake = FakeClient(RuntimeError("workflow 爆了"))

    async def fake_connect(_addr):
        return fake
    monkeypatch.setattr(rs, "_connect", fake_connect)
    r = client.post("/api/systems/sys1/tasks/T-0001/run")
    run_id = r.json()["id"]
    got = None
    for _ in range(50):
        got = client.get(f"/api/runs/{run_id}").json()
        if got["status"] != "running":
            break
        time.sleep(0.1)
    assert got["status"] == "failed" and "workflow 爆了" in got["detail"]
