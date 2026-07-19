"""TagStore 测试：分层、路径、重命名/删除级联，及 case 标签前缀重写。"""

import pytest

from eddplatform.domain.models import Case
from eddplatform.store import CaseStore, TagStore


@pytest.fixture
def tags(tmp_path):
    return TagStore(db_path=str(tmp_path / "t.db"))


def test_add_root_and_child_paths(tags):
    biz = tags.add_tag("insurance", "业务")
    quote = tags.add_tag("insurance", "报价", parent_id=biz.id)
    assert biz.path == "业务"
    assert quote.path == "业务/报价"


def test_list_is_ordered_parent_before_child(tags):
    biz = tags.add_tag("insurance", "业务")
    tags.add_tag("insurance", "报价", parent_id=biz.id)
    paths = [n.path for n in tags.list_tags("insurance")]
    assert paths == ["业务", "业务/报价"]


def test_name_cannot_contain_slash(tags):
    with pytest.raises(ValueError):
        tags.add_tag("insurance", "业务/报价")


def test_reject_duplicate_sibling(tags):
    tags.add_tag("insurance", "业务")
    with pytest.raises(ValueError):
        tags.add_tag("insurance", "业务")


def test_same_name_ok_under_different_parents(tags):
    a = tags.add_tag("insurance", "A")
    b = tags.add_tag("insurance", "B")
    tags.add_tag("insurance", "报价", parent_id=a.id)
    tags.add_tag("insurance", "报价", parent_id=b.id)   # 不同父级，允许同名
    assert {n.path for n in tags.list_tags("insurance")} >= {"A/报价", "B/报价"}


def test_missing_parent_rejected(tags):
    with pytest.raises(ValueError):
        tags.add_tag("insurance", "报价", parent_id="999")


def test_rename_returns_old_and_new_path(tags):
    biz = tags.add_tag("insurance", "业务")
    child = tags.add_tag("insurance", "报价", parent_id=biz.id)
    node, old, new = tags.rename_tag("insurance", child.id, "报价单")
    assert (old, new) == ("业务/报价", "业务/报价单")
    assert node.path == "业务/报价单"


def test_rename_parent_shifts_children_paths(tags):
    biz = tags.add_tag("insurance", "业务")
    tags.add_tag("insurance", "报价", parent_id=biz.id)
    _, old, new = tags.rename_tag("insurance", biz.id, "商务")
    assert (old, new) == ("业务", "商务")
    assert "商务/报价" in tags.paths("insurance")


def test_delete_cascades_children(tags):
    biz = tags.add_tag("insurance", "业务")
    tags.add_tag("insurance", "报价", parent_id=biz.id)
    deleted = tags.delete_tag("insurance", biz.id)
    assert set(deleted) == {"业务", "业务/报价"}
    assert tags.list_tags("insurance") == []


def test_seed_if_empty_is_idempotent(tags):
    tree = [("业务", ["报价", "对话"]), ("质量", ["回归"])]
    tags.seed_if_empty("insurance", tree)
    tags.seed_if_empty("insurance", tree)
    paths = set(tags.paths("insurance"))
    assert paths == {"业务", "业务/报价", "业务/对话", "质量", "质量/回归"}


def test_rewrite_tag_prefix_updates_matching_cases(tmp_path):
    cases = CaseStore(db_path=str(tmp_path / "c.db"))
    cases.add_case("insurance", Case(id="1", name="a", inputs="x", tags=["业务/报价"]))
    cases.add_case("insurance", Case(id="2", name="b", inputs="x", tags=["业务", "质量/回归"]))
    cases.add_case("insurance", Case(id="3", name="c", inputs="x", tags=["安全/注入"]))

    n = cases.rewrite_tag_prefix("insurance", "业务", "商务")
    assert n == 2   # #1(业务/报价) 和 #2(业务) 受影响，#3 不受影响
    assert cases.get_case("insurance", "1").tags == ["商务/报价"]
    assert cases.get_case("insurance", "2").tags == ["商务", "质量/回归"]
    assert cases.get_case("insurance", "3").tags == ["安全/注入"]
