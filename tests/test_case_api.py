"""用例管理 API 测试：CRUD + 导入导出，走 FastAPI TestClient。"""

import pytest
from fastapi.testclient import TestClient

from eddplatform.api import app as app_module
from eddplatform.store import CaseStore

SYS = "insurance"


DS = "DS-0001"


@pytest.fixture
def client(test_db):
    from eddplatform.store import DatasetStore, SystemStore
    app_module.store = CaseStore(db=test_db)
    app_module.system_store = SystemStore(db=test_db)
    app_module.dataset_store = DatasetStore(db=test_db)
    c = TestClient(app_module.app)
    c.post("/api/systems", json={"id": SYS, "name": "保险报价系统"})
    c.post(f"/api/systems/{SYS}/datasets", json={"name": "默认用例库"})
    return c


def _payload(name="quote_basic", **kw):
    return {"name": name, **kw}


def test_dataset_starts_empty(client):
    r = client.get(f"/api/systems/{SYS}/datasets/{DS}/cases")
    assert r.status_code == 200
    assert r.json() == []


def test_create_generates_id_and_persists(client):
    r = client.post(f"/api/systems/{SYS}/datasets/{DS}/cases", json=_payload())
    assert r.status_code == 201
    created = r.json()
    assert created["id"] == "quote_basic"       # 内部 id = name
    assert created["created_at"] is not None
    # 出现在 dataset 里
    cases = client.get(f"/api/systems/{SYS}/datasets/{DS}/cases").json()
    assert [c["id"] for c in cases] == ["quote_basic"]


def test_create_with_trace(client):
    r = client.post(
        f"/api/systems/{SYS}/datasets/{DS}/cases",
        json=_payload(trace={"ref": "trace-1", "url": "http://lf/t/1", "note": "算错"}),
    )
    assert r.status_code == 201
    assert r.json()["trace"]["ref"] == "trace-1"


def test_update_case(client):
    cid = client.post(f"/api/systems/{SYS}/datasets/{DS}/cases", json=_payload()).json()["id"]
    r = client.put(f"/api/systems/{SYS}/datasets/{DS}/cases/{cid}", json=_payload(name="改名"))
    assert r.status_code == 200
    assert r.json()["name"] == "改名"


def test_update_missing_is_404(client):
    r = client.put(f"/api/systems/{SYS}/datasets/{DS}/cases/999", json=_payload())
    assert r.status_code == 404


def test_delete_case(client):
    cid = client.post(f"/api/systems/{SYS}/datasets/{DS}/cases", json=_payload()).json()["id"]
    assert client.delete(f"/api/systems/{SYS}/datasets/{DS}/cases/{cid}").status_code == 204
    assert client.delete(f"/api/systems/{SYS}/datasets/{DS}/cases/{cid}").status_code == 404


def test_export_import_roundtrip(client):
    client.post(f"/api/systems/{SYS}/datasets/{DS}/cases", json=_payload(name="A"))
    client.post(f"/api/systems/{SYS}/datasets/{DS}/cases", json=_payload(name="B"))
    exported = client.get(f"/api/systems/{SYS}/datasets/{DS}/cases/export").json()
    assert len(exported) == 2

    # 导到另一个系统（replace）——目标系统与其用例库也需先注册
    client.post("/api/systems", json={"id": "cs", "name": "客服系统"})
    client.post("/api/systems/cs/datasets", json={"name": "默认用例库"})
    r = client.post(
        f"/api/systems/cs/datasets/{DS}/cases/import",
        json={"cases": exported, "mode": "replace"},
    )
    assert r.status_code == 200
    assert r.json()["total"] == 2
    assert len(client.get(f"/api/systems/cs/datasets/{DS}/cases/export").json()) == 2


def test_import_append_upserts(client):
    client.post(f"/api/systems/{SYS}/datasets/{DS}/cases", json=_payload(name="c1"))
    r = client.post(
        f"/api/systems/{SYS}/datasets/{DS}/cases/import",
        json={"cases": [{"id": "c1", "name": "c1", "description": "改"},
                        {"name": "c2"}], "mode": "append"},
    )
    body = r.json()
    assert body == {"added": 1, "updated": 1, "total": 2}


def test_import_bad_mode_is_400(client):
    r = client.post(
        f"/api/systems/{SYS}/datasets/{DS}/cases/import", json={"cases": [], "mode": "merge"}
    )
    assert r.status_code == 400
