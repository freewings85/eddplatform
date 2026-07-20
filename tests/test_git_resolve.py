"""git 解析服务：分支→最新 commit；commit→校验存在+反查分支。用临时真 git 仓测。"""
import subprocess

import pytest

from eddplatform.api.git_resolve import GitResolveError, resolve_branch, resolve_commit


def _sh(*cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _sh("git", "init", "-q", "-b", "main", cwd=r)
    _sh("git", "config", "user.email", "t@t", cwd=r)
    _sh("git", "config", "user.name", "t", cwd=r)
    (r / "a.txt").write_text("1")
    _sh("git", "add", "-A", cwd=r)
    _sh("git", "commit", "-qm", "c1", cwd=r)
    _sh("git", "checkout", "-qb", "2.3-eval", cwd=r)
    (r / "a.txt").write_text("2")
    _sh("git", "commit", "-aqm", "c2", cwd=r)
    return r


def test_resolve_branch_returns_latest_commit(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("EDD_GIT_CACHE", str(tmp_path / "cache"))
    head = _sh("git", "rev-parse", "2.3-eval", cwd=repo)
    out = resolve_branch(str(repo), "2.3-eval")
    assert out == {"branch": "2.3-eval", "commit": head}


def test_resolve_branch_unknown_raises(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("EDD_GIT_CACHE", str(tmp_path / "cache"))
    with pytest.raises(GitResolveError):
        resolve_branch(str(repo), "no-such-branch")


def test_resolve_commit_finds_branches(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("EDD_GIT_CACHE", str(tmp_path / "cache"))
    c1 = _sh("git", "rev-parse", "main", cwd=repo)
    out = resolve_commit(str(repo), c1[:10])          # 短 sha 也接受
    assert out["commit"] == c1
    assert "main" in out["branches"] and "2.3-eval" in out["branches"]


def test_resolve_commit_unknown_raises(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("EDD_GIT_CACHE", str(tmp_path / "cache"))
    with pytest.raises(GitResolveError):
        resolve_commit(str(repo), "deadbeef00")


def _add_unit(repo, path="edd_helm"):
    unit = repo / path
    (unit / "chart" / "templates").mkdir(parents=True)
    (unit / "build.sh").write_text("#!/bin/bash\ntrue\n")
    (unit / "chart" / "Chart.yaml").write_text("apiVersion: v2\nname: demo\nversion: 0.1.0\n")
    (unit / "chart" / "values.yaml").write_text(
        "services:\n  demo:\n    image: \"\"\n    port: 80\n")
    _sh("git", "add", "-A", cwd=repo)
    _sh("git", "commit", "-qm", "unit", cwd=repo)
    return _sh("git", "rev-parse", "HEAD", cwd=repo)


def test_validate_unit_ok(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("EDD_GIT_CACHE", str(tmp_path / "cache"))
    from eddplatform.api.git_resolve import validate_unit
    sha = _add_unit(repo)
    out = validate_unit(str(repo), sha, "edd_helm")
    assert out["ok"] is True and out["errors"] == []
    assert out["name"] == "demo" and out["services"] == ["demo"]


def test_validate_unit_reports_missing_pieces(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("EDD_GIT_CACHE", str(tmp_path / "cache"))
    from eddplatform.api.git_resolve import validate_unit
    sha = _sh("git", "rev-parse", "HEAD", cwd=repo)   # 没加过单元文件
    out = validate_unit(str(repo), sha, "edd_helm")
    assert out["ok"] is False
    assert any("build.sh" in e for e in out["errors"])
    assert any("Chart.yaml" in e for e in out["errors"])
