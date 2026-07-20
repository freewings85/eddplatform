"""CaseStore 持久化测试：CRUD / id 生成 / 保序 / 导入导出 / 播种。"""

import pytest

from eddplatform.domain.models import Case, CaseTrace
from eddplatform.store import CaseStore


@pytest.fixture
def store(test_db):
    return CaseStore(db=test_db)


def _case(name="用例", **kw):
    return Case(name=name, inputs="x", **kw)


def test_add_generates_id_and_timestamps(store):
    c = store.add_case("insurance", "DS-1", _case())
    assert c.id == "1"                     # 首条从 1 开始
    assert c.created_at is not None and c.updated_at is not None


def test_next_id_is_max_numeric_plus_one(store):
    store.add_case("insurance", "DS-1", _case(id="17"))
    store.add_case("insurance", "DS-1", _case(id="88"))
    c = store.add_case("insurance", "DS-1", _case())
    assert c.id == "89"


def test_add_duplicate_id_raises(store):
    store.add_case("insurance", "DS-1", _case(id="17"))
    with pytest.raises(ValueError):
        store.add_case("insurance", "DS-1", _case(id="17"))


def test_list_preserves_insertion_order(store):
    for i in ("a", "b", "c"):
        store.add_case("insurance", "DS-1", _case(id=i))
    assert [c.id for c in store.list_cases("insurance", "DS-1")] == ["a", "b", "c"]


def test_systems_are_isolated(store):
    store.add_case("insurance", "DS-1", _case(id="1"))
    store.add_case("cs", "DS-1", _case(id="1"))
    assert len(store.list_cases("insurance", "DS-1")) == 1
    assert len(store.list_cases("cs", "DS-1")) == 1


def test_get_case(store):
    store.add_case("insurance", "DS-1", _case(id="17", name="报价"))
    assert store.get_case("insurance", "DS-1", "17").name == "报价"
    assert store.get_case("insurance", "DS-1", "999") is None


def test_update_keeps_id_created_at_refreshes_updated(store):
    a = store.add_case("insurance", "DS-1", _case(id="17", name="旧"))
    updated = store.update_case("insurance", "DS-1", "17", _case(id="ignored", name="新"))
    assert updated.id == "17"
    assert updated.name == "新"
    assert updated.created_at == a.created_at
    assert updated.updated_at >= a.updated_at


def test_update_missing_raises(store):
    with pytest.raises(KeyError):
        store.update_case("insurance", "DS-1", "999", _case())


def test_delete(store):
    store.add_case("insurance", "DS-1", _case(id="17"))
    store.delete_case("insurance", "DS-1", "17")
    assert store.get_case("insurance", "DS-1", "17") is None
    with pytest.raises(KeyError):
        store.delete_case("insurance", "DS-1", "17")


def test_trace_roundtrips(store):
    t = CaseTrace(ref="trace-abc", url="http://lf/trace/abc", note="报价算错")
    store.add_case("insurance", "DS-1", _case(id="17", trace=t))
    got = store.get_case("insurance", "DS-1", "17")
    assert got.trace is not None
    assert got.trace.ref == "trace-abc"
    assert got.trace.note == "报价算错"


def test_export_returns_all(store):
    store.add_case("insurance", "DS-1", _case(id="1"))
    store.add_case("insurance", "DS-1", _case(id="2"))
    assert len(store.export_cases("insurance", "DS-1")) == 2


def test_import_append_upserts_by_id(store):
    store.add_case("insurance", "DS-1", _case(id="17", name="旧"))
    res = store.import_cases(
        "insurance", "DS-1",
        [_case(id="17", name="改"), _case(id="88", name="新增")],
        mode="append",
    )
    assert (res.added, res.updated, res.total) == (1, 1, 2)
    assert store.get_case("insurance", "DS-1", "17").name == "改"


def test_import_replace_clears_first(store):
    store.add_case("insurance", "DS-1", _case(id="17"))
    store.add_case("insurance", "DS-1", _case(id="88"))
    res = store.import_cases("insurance", "DS-1", [_case(id="900")], mode="replace")
    ids = {c.id for c in store.list_cases("insurance", "DS-1")}
    assert ids == {"900"}
    assert res.total == 1


def test_import_rejects_bad_mode(store):
    with pytest.raises(ValueError):
        store.import_cases("insurance", "DS-1", [], mode="merge")


def test_persists_across_instances(test_db):
    CaseStore(db=test_db).add_case("insurance", "DS-1", _case(id="17"))
    assert CaseStore(db=test_db).get_case("insurance", "DS-1", "17") is not None
