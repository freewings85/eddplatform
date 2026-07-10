"""Harbor 薄壳：镜像引用 + tag 校验（可选）。渲染 manifest 见 orchestration/manifest.py。

平台只做：拼 image ref、（可用时）校验 tag 存在。真实拉取 / 部署交给底座。
"""

from __future__ import annotations

import os

import httpx

from eddplatform.domain.models import Module, SystemVersion

_ENV = ("HARBOR_URL", "HARBOR_USER", "HARBOR_TOKEN")


def available() -> bool:
    return all(os.environ.get(k) for k in _ENV)


def image_ref(project: str, repo: str, tag: str) -> str:
    """拼出 ``<HARBOR_URL>/<project>/<repo>:<tag>``；未配置时用 'registry' 占位。"""
    base = os.environ.get("HARBOR_URL", "registry").rstrip("/")
    return f"{base}/{project}/{repo}:{tag}"


def _http() -> httpx.Client:
    """构造 Harbor HTTP 客户端（Basic auth + 超时）。测试可 monkeypatch 换 MockTransport。"""
    return httpx.Client(
        auth=(os.environ["HARBOR_USER"], os.environ["HARBOR_TOKEN"]), timeout=15.0)


def _artifacts_base(project: str, repo: str) -> str:
    base = os.environ["HARBOR_URL"].rstrip("/")
    return f"{base}/api/v2.0/projects/{project}/repositories/{repo}/artifacts"


def tag_exists(project: str, repo: str, tag: str) -> bool:
    """校验 Harbor 上该 tag 是否存在（需配置 Harbor；否则报错）。"""
    if not available():
        raise RuntimeError(
            "校验 Harbor tag 需要配置 HARBOR_URL / HARBOR_USER / HARBOR_TOKEN。")
    with _http() as client:
        resp = client.get(f"{_artifacts_base(project, repo)}/{tag}")
    return resp.status_code == 200


def artifact_digest(project: str, repo: str, tag: str) -> str:
    """取某 tag 的镜像 digest（按 digest 钉死可复现）。需配置 Harbor。"""
    if not available():
        raise RuntimeError(
            "读取 Harbor digest 需要配置 HARBOR_URL / HARBOR_USER / HARBOR_TOKEN。")
    with _http() as client:
        resp = client.get(f"{_artifacts_base(project, repo)}/{tag}")
    resp.raise_for_status()
    return resp.json()["digest"]


def list_tags(project: str, repo: str) -> list[str]:
    """列该 repo 下所有 artifact 的 tag 名（扁平化）。需配置 Harbor。"""
    if not available():
        raise RuntimeError(
            "列 Harbor tag 需要配置 HARBOR_URL / HARBOR_USER / HARBOR_TOKEN。")
    with _http() as client:
        resp = client.get(_artifacts_base(project, repo))
    resp.raise_for_status()
    tags: list[str] = []
    for artifact in resp.json():
        for t in artifact.get("tags") or []:
            tags.append(t["name"])
    return tags


def verify_pins(modules: list[Module], version: SystemVersion, project: str) -> None:
    """校验 SystemVersion 钉住的每个 tag 都在 Harbor（配了 Harbor 才生效）。

    未配置 Harbor：安全跳过（离线/CI 不阻断）。有缺失：抛列出全部 ``<module>:<tag>`` 的
    可操作错误——发布前预检，早失败胜过部署时拉不到镜像。
    """
    if not available():
        return
    missing = []
    for m in modules:
        tag = version.module_pins.get(m.name)
        if tag is None:
            continue
        if not tag_exists(project, m.name, tag):
            missing.append(f"{m.name}:{tag}")
    if missing:
        raise RuntimeError(
            f"Harbor 项目 {project!r} 缺少以下钉住镜像 tag：{', '.join(missing)}")
