"""CaseStore 持久化测试：CRUD / id=name / name 唯一 / 保序 / 导入导出。"""

import pytest

from eddplatform.domain.models import Case, CaseTrace
from eddplatform.store import CaseStore


@pytest.fixture
def store(test_db):
    return CaseStore(db=test_db)


def _case(name="case_a", **kw):
    return Case(name=name, **kw)


def test_add_sets_internal_id_to_name(store):
    c = store.add_case("insurance", "DS-1", _case(name="quote_basic"))
    assert c.id == "quote_basic"
    assert c.created_at is not None and c.updated_at is not None


def test_add_duplicate_name_raises(store):
    store.add_case("insurance", "DS-1", _case(name="quote_basic"))
    with pytest.raises(ValueError):
        store.add_case("insurance", "DS-1", _case(name="quote_basic"))


def test_list_preserves_insertion_order(store):
    for i in ("a", "b", "c"):
        store.add_case("insurance", "DS-1", _case(name=i))
    assert [c.id for c in store.list_cases("insurance", "DS-1")] == ["a", "b", "c"]


def test_systems_are_isolated(store):
    store.add_case("insurance", "DS-1", _case(name="x"))
    store.add_case("cs", "DS-1", _case(name="x"))
    assert len(store.list_cases("insurance", "DS-1")) == 1
    assert len(store.list_cases("cs", "DS-1")) == 1


def test_get_case(store):
    store.add_case("insurance", "DS-1", _case(name="quote_basic", description="报价"))
    assert store.get_case("insurance", "DS-1", "quote_basic").description == "报价"
    assert store.get_case("insurance", "DS-1", "nope") is None


def test_update_rename_keeps_internal_id(store):
    """改 name 不改内部 id（任务勾选的 case_ids 引用不被打断）。"""
    a = store.add_case("insurance", "DS-1", _case(name="old_name"))
    updated = store.update_case("insurance", "DS-1", "old_name", _case(name="new_name"))
    assert updated.id == "old_name"
    assert updated.name == "new_name"
    assert updated.created_at == a.created_at
    assert updated.updated_at >= a.updated_at


def test_update_to_conflicting_name_raises(store):
    store.add_case("insurance", "DS-1", _case(name="a"))
    store.add_case("insurance", "DS-1", _case(name="b"))
    with pytest.raises(ValueError):
        store.update_case("insurance", "DS-1", "b", _case(name="a"))


def test_update_missing_raises(store):
    with pytest.raises(KeyError):
        store.update_case("insurance", "DS-1", "nope", _case())


def test_delete(store):
    store.add_case("insurance", "DS-1", _case(name="x"))
    store.delete_case("insurance", "DS-1", "x")
    assert store.get_case("insurance", "DS-1", "x") is None
    with pytest.raises(KeyError):
        store.delete_case("insurance", "DS-1", "x")


def test_trace_roundtrips(store):
    t = CaseTrace(ref="trace-abc", url="http://lf/trace/abc", note="报价算错")
    store.add_case("insurance", "DS-1", _case(name="quote_basic", trace=t))
    got = store.get_case("insurance", "DS-1", "quote_basic")
    assert got.trace is not None
    assert got.trace.ref == "trace-abc"
    assert got.trace.note == "报价算错"


def test_export_returns_all(store):
    store.add_case("insurance", "DS-1", _case(name="a"))
    store.add_case("insurance", "DS-1", _case(name="b"))
    assert len(store.export_cases("insurance", "DS-1")) == 2


def test_import_append_upserts_by_id(store):
    store.add_case("insurance", "DS-1", _case(name="quote_basic", description="旧"))
    res = store.import_cases(
        "insurance", "DS-1",
        [Case(id="quote_basic", name="quote_basic", description="改"),
         Case(id="quote_extra", name="quote_extra", description="新增")],
        mode="append",
    )
    assert (res.added, res.updated, res.total) == (1, 1, 2)
    assert store.get_case("insurance", "DS-1", "quote_basic").description == "改"


def test_import_replace_clears_first(store):
    store.add_case("insurance", "DS-1", _case(name="a"))
    store.add_case("insurance", "DS-1", _case(name="b"))
    res = store.import_cases("insurance", "DS-1",
                             [Case(id="only", name="only")], mode="replace")
    ids = {c.id for c in store.list_cases("insurance", "DS-1")}
    assert ids == {"only"}
    assert res.total == 1


def test_import_rejects_bad_mode(store):
    with pytest.raises(ValueError):
        store.import_cases("insurance", "DS-1", [], mode="merge")


def test_persists_across_instances(test_db):
    CaseStore(db=test_db).add_case("insurance", "DS-1", _case(name="x"))
    assert CaseStore(db=test_db).get_case("insurance", "DS-1", "x") is not None
