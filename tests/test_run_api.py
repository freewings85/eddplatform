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

    async def start_workflow(self, wf, arg, *, id, task_queue, execution_timeout=None,
                             result_type=None):
        self.started.append((id, task_queue, arg))
        return FakeHandle(self.out)


@pytest.fixture()
def client(test_db, monkeypatch):
    import eddplatform.api.app as app_module
    from eddplatform.store import (CaseStore, DatasetStore, EvalProgramStore, RunStore,
                                   SystemStore, TagStore, TaskStore)
    for attr, obj in [("store", CaseStore(db=test_db)), ("tag_store", TagStore(db=test_db)),
                      ("dataset_store", DatasetStore(db=test_db)),
                      ("system_store", SystemStore(db=test_db)),
                      ("task_store", TaskStore(db=test_db)),
                      ("eval_program_store", EvalProgramStore(db=test_db)),
                      ("run_store", RunStore(db=test_db))]:
        monkeypatch.setattr(app_module, attr, obj)
    c = TestClient(app_module.app)
    c.post("/api/systems", json={"id": "sys1", "name": "系统1"})
    c.post("/api/systems/sys1/datasets", json={"name": "默认用例库", "workflow": "demo-eval"})   # DS-0001
    c.post("/api/systems/sys1/tasks", json={
        "name": "冒烟", "system_id": "sys1", "dataset_id": "DS-0001",
        "preconditions": [{"kind": "start_system", "git_url": "/repo", "branch": "2.3-eval", "commit": "abc123def"}]})
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


def test_run_uses_selected_cases_only(client, monkeypatch):
    """task.case_ids 勾选清单 → 只把选中的（且 enabled）用例交给 workflow。"""
    import eddplatform.api.run_service as rs
    for name in ("c1", "c2", "c3"):
        client.post("/api/systems/sys1/datasets/DS-0001/cases", json={"name": name})
    client.post("/api/systems/sys1/tasks", json={
        "name": "选例", "system_id": "sys1", "dataset_id": "DS-0001", "case_ids": ["c1", "c3"],
        "preconditions": [{"kind": "start_system", "git_url": "/repo", "branch": "b", "commit": "c0ffee1"}]})
    out = RunTaskOutput(namespace="ns", status="up")
    fake = FakeClient(out)

    async def fake_connect(_addr):
        return fake
    monkeypatch.setattr(rs, "_connect", fake_connect)
    r = client.post("/api/systems/sys1/tasks/T-0002/run")
    assert r.status_code == 202
    inp = fake.started[0][2]
    assert len(inp.case_groups) == 1           # 旧单库任务归一成单分组
    assert inp.case_groups[0].cases == ["c1", "c3"]   # 契约：只传用例 name
    assert inp.case_groups[0].dataset == "默认用例库"


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


def test_run_derives_eval_code_from_dataset_workflow(client, monkeypatch):
    """逐用例分派的 workflow 名来自任务选定的用例库（dataset.workflow）。"""
    import eddplatform.api.run_service as rs
    client.post("/api/systems/sys1/datasets/DS-0001/cases", json={"name": "c1"})
    client.post("/api/systems/sys1/tasks", json={
        "name": "评估任务", "system_id": "sys1", "dataset_id": "DS-0001",
        "preconditions": [
            {"kind": "start_system", "git_url": "/repo", "branch": "b", "commit": "c0ffee1"}]})
    fake = FakeClient(RunTaskOutput(namespace="ns", status="up"))

    async def fake_connect(_addr):
        return fake
    monkeypatch.setattr(rs, "_connect", fake_connect)
    r = client.post("/api/systems/sys1/tasks/T-0002/run")
    assert r.status_code == 202
    inp = fake.started[0][2]
    assert inp.case_groups[0].workflow == "demo-eval"
    assert inp.case_groups[0].cases == ["c1"]


def test_run_multi_case_sets_builds_groups(client, monkeypatch):
    """新格式 case_sets：多个用例库 → 逐组（dataset/workflow/cases）传给 workflow。"""
    import eddplatform.api.run_service as rs
    client.post("/api/systems/sys1/datasets/DS-0001/cases", json={"name": "a1"})
    r = client.post("/api/systems/sys1/datasets",
                    json={"name": "另一个库", "workflow": "other-eval"})
    ds2 = r.json()["id"]
    for name in ("b1", "b2"):
        client.post(f"/api/systems/sys1/datasets/{ds2}/cases", json={"name": name})
    client.post("/api/systems/sys1/tasks", json={
        "name": "多库任务", "system_id": "sys1",
        "case_sets": [
            {"dataset_id": "DS-0001", "case_ids": ["a1"]},
            {"dataset_id": ds2, "case_ids": ["b1", "b2"]},
        ],
        "preconditions": [
            {"kind": "start_system", "git_url": "/repo", "branch": "b", "commit": "c0ffee1"}]})
    fake = FakeClient(RunTaskOutput(namespace="ns", status="up"))

    async def fake_connect(_addr):
        return fake
    monkeypatch.setattr(rs, "_connect", fake_connect)
    r = client.post("/api/systems/sys1/tasks/T-0002/run")
    assert r.status_code == 202
    groups = fake.started[0][2].case_groups
    assert [(g.dataset, g.workflow, g.cases) for g in groups] == [
        ("默认用例库", "demo-eval", ["a1"]),
        ("另一个库", "other-eval", ["b1", "b2"]),
    ]


def test_run_rejects_dataset_without_workflow(client, monkeypatch):
    """有用例但库没配 workflow → 409 明确提示，而不是悄悄不评。"""
    import eddplatform.api.run_service as rs
    client.post("/api/systems/sys1/datasets", json={"name": "无workflow库"})   # DS-0002
    client.post("/api/systems/sys1/datasets/DS-0002/cases", json={"name": "c1"})
    client.post("/api/systems/sys1/tasks", json={
        "name": "t2", "system_id": "sys1", "dataset_id": "DS-0002",
        "preconditions": [
            {"kind": "start_system", "git_url": "/repo", "branch": "b", "commit": "c0ffee1"}]})
    fake = FakeClient(RunTaskOutput(namespace="ns", status="up"))

    async def fake_connect(_addr):
        return fake
    monkeypatch.setattr(rs, "_connect", fake_connect)
    r = client.post("/api/systems/sys1/tasks/T-0002/run")
    assert r.status_code == 409 and "workflow" in r.json()["detail"]
