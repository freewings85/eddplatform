"""RunStore：运行记录 + 逐用例结果（真 MySQL 测试库）。"""
from eddplatform.domain.models import CaseRunResult, RunRecord, RunStatus
from eddplatform.store.run_store import RunStore


def test_create_get_list_finish(test_db):
    rs = RunStore(db=test_db)
    run = rs.create(RunRecord(system_id="s1", task_id="T-0001", task_name="冒烟"))
    assert run.id.startswith("R-") and run.created_at is not None
    assert rs.list("s1")[0].id == run.id
    assert rs.list("other") == []
    rs.finish(run.id, RunStatus.SUCCEEDED, versions={"system": "abc"},
              outcomes=[{"kind": "start_system", "status": "ok"}], detail="")
    got = rs.get(run.id)
    assert got.status == RunStatus.SUCCEEDED and got.versions == {"system": "abc"}
    assert got.finished_at is not None


def test_case_results_roundtrip(test_db):
    rs = RunStore(db=test_db)
    run = rs.create(RunRecord(system_id="s1", task_id="T-0001"))
    rs.add_case_result(run.id, CaseRunResult(case_id="c1", status="passed", scores={"judge": 1.0}))
    rs.add_case_result(run.id, CaseRunResult(case_id="c2", status="failed", detail="工具没调"))
    got = rs.case_results(run.id)
    assert [c.case_id for c in got] == ["c1", "c2"]
    assert got[0].scores == {"judge": 1.0}
