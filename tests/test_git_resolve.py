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
