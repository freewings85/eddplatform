"""标签管理 API 测试：CRUD + 重命名联动 case 标签路径。"""

import pytest
from fastapi.testclient import TestClient

from eddplatform.api import app as app_module
from eddplatform.store import CaseStore, TagStore

SYS = "insurance"


@pytest.fixture
def client(test_db):
    from eddplatform.store import SystemStore
    app_module.store = CaseStore(db=test_db)
    app_module.tag_store = TagStore(db=test_db)
    app_module.system_store = SystemStore(db=test_db)
    c = TestClient(app_module.app)
    c.post("/api/systems", json={"id": SYS, "name": "保险报价系统"})
    return c


def _add_tag(client, name, parent_id=None):
    return client.post(
        f"/api/systems/{SYS}/tags", json={"name": name, "parent_id": parent_id}
    ).json()


def test_create_tree_and_list(client):
    biz = _add_tag(client, "业务")
    _add_tag(client, "报价", biz["id"])
    paths = [t["path"] for t in client.get(f"/api/systems/{SYS}/tags").json()]
    assert paths == ["业务", "业务/报价"]


def test_duplicate_sibling_is_409(client):
    _add_tag(client, "业务")
    r = client.post(f"/api/systems/{SYS}/tags", json={"name": "业务"})
    assert r.status_code == 409


def test_rename_also_rewrites_case_tags(client):
    biz = _add_tag(client, "业务")
    _add_tag(client, "报价", biz["id"])
    # 一条用例用了 业务/报价
    client.post(
        f"/api/systems/{SYS}/cases",
        json={"name": "报价用例", "inputs": "x", "tags": ["业务/报价"]},
    )
    # 重命名父标签 业务 -> 商务
    r = client.put(f"/api/systems/{SYS}/tags/{biz['id']}", json={"name": "商务"})
    assert r.status_code == 200
    # case 上的标签路径被联动改写
    cases = client.get(f"/api/systems/{SYS}/dataset").json()["cases"]
    assert cases[0]["tags"] == ["商务/报价"]


def test_delete_cascades(client):
    biz = _add_tag(client, "业务")
    _add_tag(client, "报价", biz["id"])
    assert client.delete(f"/api/systems/{SYS}/tags/{biz['id']}").status_code == 204
    assert client.get(f"/api/systems/{SYS}/tags").json() == []


def test_rename_missing_is_404(client):
    r = client.put(f"/api/systems/{SYS}/tags/999", json={"name": "x"})
    assert r.status_code == 404
