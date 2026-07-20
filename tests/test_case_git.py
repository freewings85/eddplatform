"""用例仓 git 双向：导入（git→库缓存，全量重建）与导出（库→git，逐用例一文件）。"""
import subprocess

import pytest

from eddplatform.domain.models import Case, DatasetInfo, System


def _sh(*cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def cases_repo(tmp_path, monkeypatch):
    """裸远端 + 工作克隆：guide/ 和 shops/ 两个用例库文件夹。"""
    monkeypatch.setenv("EDD_GIT_CACHE", str(tmp_path / "cache"))
    origin = tmp_path / "origin.git"
    _sh("git", "init", "-q", "--bare", "-b", "main", str(origin))
    work = tmp_path / "work"
    _sh("git", "clone", "-q", str(origin), str(work))
    _sh("git", "-C", str(work), "config", "user.email", "t@t")
    _sh("git", "-C", str(work), "config", "user.name", "t")
    (work / "guide").mkdir()
    (work / "guide" / "cases.yaml").write_text(
        "group: guide\ncases:\n"
        "  - id: g1\n    turns: [{user: \"你好\"}]\n    expect: {judge: {rubric: \"友好\"}}\n"
        "  - id: g2\n    turns: [{user: \"介绍\"}]\n", encoding="utf-8")
    (work / "shops" / "sub").mkdir(parents=True)
    (work / "shops" / "s.yaml").write_text(
        "cases:\n  - id: s1\n    turns: [{user: \"找店\"}]\n", encoding="utf-8")
    (work / "README.md").write_text("not a case file")
    _sh("git", "-C", str(work), "add", "-A")
    _sh("git", "-C", str(work), "commit", "-qm", "init cases")
    _sh("git", "-C", str(work), "push", "-q", "origin", "main")
    return origin


def _system(origin) -> System:
    return System(id="sys1", name="系统1", cases_git_url=str(origin), cases_branch="main")


def test_import_discovers_folders_and_rebuilds(test_db, cases_repo):
    from eddplatform.api.case_git import import_from_git
    from eddplatform.store import CaseStore, DatasetStore
    ds, cs = DatasetStore(db=test_db), CaseStore(db=test_db)
    report = import_from_git(_system(cases_repo), ds, cs)
    assert len(report["commit"]) == 40
    libs = {d.path: d for d in ds.list("sys1")}
    assert set(libs) == {"guide", "shops"}
    assert [c.id for c in cs.list_cases("sys1", libs["guide"].id)] == ["g1", "g2"]
    g1 = cs.get_case("sys1", libs["guide"].id, "g1")
    assert "group/guide" in g1.tags
    # 再次导入 = 全量重建（幂等）
    report2 = import_from_git(_system(cases_repo), ds, cs)
    assert {(l["path"], l["count"]) for l in report2["libraries"]} == {("guide", 2), ("shops", 1)}


def test_export_writes_one_file_per_case_and_pushes(test_db, cases_repo, tmp_path):
    from eddplatform.api.case_git import export_to_git, import_from_git
    from eddplatform.store import CaseStore, DatasetStore
    ds, cs = DatasetStore(db=test_db), CaseStore(db=test_db)
    system = _system(cases_repo)
    import_from_git(system, ds, cs)
    guide = next(d for d in ds.list("sys1") if d.path == "guide")
    # 库里改一条 + 加一条
    cs.update_case("sys1", guide.id, "g1", Case(id="g1", name="改过的g1", inputs='[{"user": "你好"}]'))
    cs.add_case("sys1", guide.id, Case(id="g3", name="新增", inputs='[{"user": "新"}]'))
    out = export_to_git(system, guide, cs.list_cases("sys1", guide.id))
    assert out["files"] == 3
    # 远端应有 逐用例文件；再导入回来内容一致（回环）
    report = import_from_git(system, ds, cs)
    guide2 = next(d for d in ds.list("sys1") if d.path == "guide")
    ids = [c.id for c in cs.list_cases("sys1", guide2.id)]
    assert sorted(ids) == ["g1", "g2", "g3"]
    assert cs.get_case("sys1", guide2.id, "g1").name == "改过的g1"
    assert report["commit"] == out["commit"]
