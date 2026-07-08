"""Jira 只写适配器：薄、可选、离线兜底 —— 照 evals/adapters/langfuse.py 的模式。

新建需求时若配了 Jira（``JIRA_URL`` / ``JIRA_EMAIL`` / ``JIRA_TOKEN``）→ 推一个
issue，回填 key + url；未配 → 手填 / 关联已有 key，平台照常工作（离线 / CI 无阻）。
本轮只写（``create_issue``），不从 Jira 拉状态。复用已有 ``httpx``，不新增依赖。
"""

from __future__ import annotations

import os

_ENV = ("JIRA_URL", "JIRA_EMAIL", "JIRA_TOKEN")


def available() -> bool:
    """三项环境变量齐了才算配置好 Jira。"""
    return all(os.environ.get(k) for k in _ENV)


def issue_url(key: str) -> str:
    """由 JIRA_URL 拼出 issue 的 browse 链接。"""
    base = os.environ.get("JIRA_URL", "").rstrip("/")
    return f"{base}/browse/{key}"


def create_issue(project: str, summary: str, description: str = "",
                 issue_type: str = "Story") -> dict:
    """推一个 Jira issue，返回 ``{"key", "url"}``。未配置时抛可操作的错误。"""
    if not available():
        raise RuntimeError(
            "推送需求需要 Jira：设置 JIRA_URL / JIRA_EMAIL / JIRA_TOKEN；"
            "未配置可改「关联已有 Jira 号」或「暂不关联」，平台其余流程不受阻。"
        )
    import httpx

    base = os.environ["JIRA_URL"].rstrip("/")
    resp = httpx.post(
        f"{base}/rest/api/2/issue",
        auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_TOKEN"]),
        json={"fields": {
            "project": {"key": project},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issue_type},
        }},
        timeout=30.0,
    )
    resp.raise_for_status()
    key = resp.json()["key"]
    return {"key": key, "url": issue_url(key)}
