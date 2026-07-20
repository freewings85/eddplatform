"""git 解析：新建评估任务时把「分支/commit」固化成双字段。

- ``resolve_branch``：``git ls-remote`` 拿某分支当前指向的 commit（不落盘，快）。
- ``resolve_commit``：镜像缓存仓（``EDD_GIT_CACHE``，默认 ~/.cache/eddplatform/git）
  里校验 commit 存在，并反查包含它的分支。首次会 ``clone --mirror``，之后增量 fetch。
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


class GitResolveError(Exception):
    pass


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise GitResolveError(proc.stderr.strip() or proc.stdout.strip() or f"命令失败: {cmd}")
    return proc.stdout


def _cache_dir(git_url: str) -> Path:
    root = Path(os.environ.get("EDD_GIT_CACHE") or Path.home() / ".cache" / "eddplatform" / "git")
    return root / hashlib.sha1(git_url.encode()).hexdigest()[:16]


def _mirror(git_url: str) -> Path:
    """镜像缓存仓：不存在则 clone --mirror，存在则 fetch 刷新。"""
    d = _cache_dir(git_url)
    if not d.exists():
        d.parent.mkdir(parents=True, exist_ok=True)
        _run(["git", "clone", "--mirror", "--quiet", git_url, str(d)])
    else:
        _run(["git", "-C", str(d), "fetch", "--prune", "--quiet"])
    return d


def resolve_branch(git_url: str, branch: str) -> dict:
    """分支 → 该分支当前最新 commit。"""
    out = _run(["git", "ls-remote", git_url, f"refs/heads/{branch}"])
    line = out.strip().splitlines()
    if not line:
        raise GitResolveError(f"仓库里没有分支 {branch!r}")
    return {"branch": branch, "commit": line[0].split()[0]}


def validate_unit(git_url: str, ref: str, path: str = ".") -> dict:
    """在 仓库@ref 里校验单元文件夹是否满足 EDD 接入规范（不落工作区，直接读对象库）。

    检查：``.eddplatform.yaml`` 存在且 kind/build/chart 齐全；build 脚本存在；
    chart 目录存在且有 Chart.yaml。返回 {ok, errors, kind, build, chart, services}。
    """
    import posixpath

    import yaml

    d = _mirror(git_url)
    try:
        full = _run(["git", "-C", str(d), "rev-parse", "--verify", f"{ref}^{{commit}}"]).strip()
    except GitResolveError:
        raise GitResolveError(f"仓库里找不到 ref {ref!r}")

    prefix = "" if path in (".", "") else path.strip("/") + "/"

    def _exists(p: str) -> bool:
        proc = subprocess.run(["git", "-C", str(d), "cat-file", "-e", f"{full}:{p}"],
                              capture_output=True, text=True, timeout=60)
        return proc.returncode == 0

    def _norm(rel: str) -> str:
        return posixpath.normpath(posixpath.join(prefix, rel))

    errors: list[str] = []
    out: dict = {"ok": False, "errors": errors, "name": None, "kind": None, "build": None,
                 "chart": None, "services": []}
    conv = prefix + ".eddplatform.yaml"
    if not _exists(conv):
        errors.append(f"缺少约定文件 {conv}（下载规范示例查看要求）")
        return out
    try:
        data = yaml.safe_load(_run(["git", "-C", str(d), "show", f"{full}:{conv}"])) or {}
    except GitResolveError as e:
        errors.append(f"读取 {conv} 失败: {e}")
        return out
    missing = [k for k in ("name", "kind", "build", "chart") if not data.get(k)]
    if missing:
        errors.append(f"{conv} 缺少必填字段: {', '.join(missing)}")
        return out
    import re as _re
    if not _re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(data["name"])):
        errors.append(f"name 必须是小写字母/数字/中划线，得到 {data['name']!r}")
    out.update(name=data["name"], kind=data["kind"], build=data["build"], chart=data["chart"],
               services=list(data.get("services", [])))
    if data["kind"] not in ("system", "eval"):
        errors.append(f"kind 必须是 system 或 eval，得到 {data['kind']!r}")
    build_path = _norm(data["build"])
    if not _exists(build_path):
        errors.append(f"构建脚本不存在: {build_path}")
    chart_path = _norm(data["chart"])
    if not _exists(chart_path + "/Chart.yaml"):
        errors.append(f"helm chart 无效: {chart_path}/Chart.yaml 不存在")
    out["ok"] = not errors
    return out


def resolve_commit(git_url: str, commit: str) -> dict:
    """commit（可短 sha）→ 校验存在 + 补全全 sha + 反查包含它的分支。"""
    d = _mirror(git_url)
    try:
        full = _run(["git", "-C", str(d), "rev-parse", "--verify", f"{commit}^{{commit}}"]).strip()
    except GitResolveError:
        raise GitResolveError(f"仓库里找不到 commit {commit!r}")
    out = _run(["git", "-C", str(d), "branch", "--contains", full,
                "--format=%(refname:short)"])
    branches = [b.strip() for b in out.splitlines() if b.strip()]
    return {"commit": full, "branches": branches}
