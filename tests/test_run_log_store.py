"""运行控制台日志：store 往返（多行拆分/增量取）+ logs API。"""
import pytest
from fastapi.testclient import TestClient

from eddplatform.domain.models import RunRecord
from eddplatform.store.run_log_store import RunLogStore
from eddplatform.store.run_store import RunStore


def test_append_splits_lines_and_lists_in_order(test_db):
    s = RunLogStore(test_db)
    s.append("R-1", "第一行\n第二行")
    s.append("R-2", "别的运行的日志")
    lines = s.list("R-1")
    assert [ln["line"] for ln in lines] == ["第一行", "第二行"]
    assert all(ln["ts"] for ln in lines)


def test_append_strips_ansi_colors(test_db):
    s = RunLogStore(test_db)
    s.append("R-1", "\x1b[36mINFO\x1b[0m[0000] Importing image(s)")
    assert s.list("R-1")[0]["line"] == "INFO[0000] Importing image(s)"


def test_incremental_after(test_db):
    s = RunLogStore(test_db)
    s.append("R-1", "old")
    last = s.list("R-1")[-1]["id"]
    s.append("R-1", "$ helm upgrade --install chatagent …")
    inc = s.list("R-1", after=last)
    assert [ln["line"] for ln in inc] == ["$ helm upgrade --install chatagent …"]
    assert s.list("R-1", after=inc[-1]["id"]) == []


@pytest.fixture()
def client(test_db, monkeypatch):
    import eddplatform.api.app as app_module
    monkeypatch.setattr(app_module, "run_store", RunStore(db=test_db))
    monkeypatch.setattr(app_module, "run_log_store", RunLogStore(test_db))
    return TestClient(app_module.app)


def test_logs_api_incremental(client, test_db):
    run = RunStore(db=test_db).create(RunRecord(system_id="sys1", task_id="T-1"))
    RunLogStore(test_db).append(run.id, "RUN 已提交\n$ git clone …")

    assert client.get("/api/runs/R-nope/logs").status_code == 404

    page = client.get(f"/api/runs/{run.id}/logs").json()
    assert [ln["line"] for ln in page["lines"]] == ["RUN 已提交", "$ git clone …"]

    again = client.get(f"/api/runs/{run.id}/logs?after={page['last_id']}").json()
    assert again["lines"] == [] and again["last_id"] == page["last_id"]
