"""Jira 适配器：薄、只写、可选、离线兜底（不打网络）。"""

import pytest

from eddplatform.integrations import jira

_ENV = ("JIRA_URL", "JIRA_EMAIL", "JIRA_TOKEN")


def _clear(mp):
    for k in _ENV:
        mp.delenv(k, raising=False)


def test_available_false_without_env(monkeypatch):
    _clear(monkeypatch)
    assert jira.available() is False


def test_available_true_with_full_env(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://acme.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "a@b.c")
    monkeypatch.setenv("JIRA_TOKEN", "tok")
    assert jira.available() is True


def test_create_issue_raises_when_unconfigured(monkeypatch):
    """未配 Jira 时给出可操作的错误，平台其余流程照常（手填 key）。"""
    _clear(monkeypatch)
    with pytest.raises(RuntimeError, match="Jira"):
        jira.create_issue("PROJ", "标题", "描述")


def test_issue_url_builds_browse_link(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://acme.atlassian.net/")
    assert jira.issue_url("PROJ-2043") == "https://acme.atlassian.net/browse/PROJ-2043"
