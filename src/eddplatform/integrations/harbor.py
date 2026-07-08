"""Harbor 薄壳：镜像引用 + tag 校验（可选）。渲染 manifest 见 orchestration/manifest.py。

平台只做：拼 image ref、（可用时）校验 tag 存在。真实拉取 / 部署交给底座。
"""

from __future__ import annotations

import os

_ENV = ("HARBOR_URL", "HARBOR_USER", "HARBOR_TOKEN")


def available() -> bool:
    return all(os.environ.get(k) for k in _ENV)


def image_ref(project: str, repo: str, tag: str) -> str:
    """拼出 ``<HARBOR_URL>/<project>/<repo>:<tag>``；未配置时用 'registry' 占位。"""
    base = os.environ.get("HARBOR_URL", "registry").rstrip("/")
    return f"{base}/{project}/{repo}:{tag}"


def tag_exists(project: str, repo: str, tag: str) -> bool:
    """校验 Harbor 上该 tag 是否存在（需配置 Harbor；否则报错）。"""
    if not available():
        raise RuntimeError(
            "校验 Harbor tag 需要配置 HARBOR_URL / HARBOR_USER / HARBOR_TOKEN。"
        )
    import httpx

    base = os.environ["HARBOR_URL"].rstrip("/")
    url = f"{base}/api/v2.0/projects/{project}/repositories/{repo}/artifacts/{tag}"
    resp = httpx.get(url, auth=(os.environ["HARBOR_USER"], os.environ["HARBOR_TOKEN"]),
                     timeout=15.0)
    return resp.status_code == 200
