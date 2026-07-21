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
    """在 仓库@ref 里校验单元文件夹是否满足 EDD 约定（不落工作区，直接读对象库）。

    约定 = 标准 helm chart + 构建脚本：``build.sh`` 存在；``chart/Chart.yaml``
    存在且 ``name`` 合法（helm release 名）；``chart/values.yaml`` 有
    ``services.<服务名>.image`` 挂点。返回 {ok, errors, name, services}。
    """
    import re as _re

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

    def _read_yaml(p: str) -> dict:
        return yaml.safe_load(_run(["git", "-C", str(d), "show", f"{full}:{p}"])) or {}

    errors: list[str] = []
    out: dict = {"ok": False, "errors": errors, "name": None, "services": []}

    build = prefix + "build.sh"
    if not _exists(build):
        errors.append(f"缺少构建脚本 {build}（下载规范示例查看要求）")

    chart_yaml = prefix + "chart/Chart.yaml"
    if not _exists(chart_yaml):
        errors.append(f"缺少 helm chart：{chart_yaml} 不存在")
        return out
    try:
        chart = _read_yaml(chart_yaml)
    except (GitResolveError, yaml.YAMLError) as e:
        errors.append(f"读取 {chart_yaml} 失败: {e}")
        return out
    name = chart.get("name")
    if not name or not _re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(name)):
        errors.append(f"Chart.yaml 的 name 无效（作 helm release 名，需小写字母/数字/中划线）: {name!r}")
    else:
        out["name"] = str(name)

    values_yaml = prefix + "chart/values.yaml"
    if not _exists(values_yaml):
        errors.append(f"缺少 {values_yaml}（需要 services.<服务名>.image 挂点）")
    else:
        try:
            values = _read_yaml(values_yaml)
        except (GitResolveError, yaml.YAMLError) as e:
            values = {}
            errors.append(f"读取 {values_yaml} 失败: {e}")
        services = values.get("services") or {}
        if not isinstance(services, dict) or not services:
            errors.append("values.yaml 缺少 services.<服务名> 声明（服务名=集群内 DNS 名）")
        else:
            out["services"] = list(services.keys())
            for svc, cfg in services.items():
                if not isinstance(cfg, dict) or "image" not in cfg:
                    errors.append(f"values.yaml 的 services.{svc} 缺少 image 挂点")

    out["ok"] = not errors
    return out


def scan_infra(git_url: str, ref: str, path: str = "build/infra") -> dict:
    """扫描 仓库@ref 的基础组件目录：每个子文件夹 = 一个可选部署的基础组件。

    组件 = **纯 chart 单元**（``<path>/<组件名>/chart/``，无需 build.sh；
    文件夹名即组件类型，如 kafka / postgres）。返回每个组件的 helm release 名
    与服务地址（values.yaml 的 ``services.<服务名>.port``）——页面据此提示用户
    「部署配置里相应的值要改成 <服务名>:<端口>」。
    """
    import yaml

    d = _mirror(git_url)
    try:
        full = _run(["git", "-C", str(d), "rev-parse", "--verify", f"{ref}^{{commit}}"]).strip()
    except GitResolveError:
        raise GitResolveError(f"仓库里找不到 ref {ref!r}")
    prefix = path.strip("/")
    proc = subprocess.run(
        ["git", "-C", str(d), "ls-tree", "-z", full, f"{prefix}/"],
        capture_output=True, text=True, timeout=60)
    components: list[dict] = []
    for entry in (proc.stdout or "").split("\0"):
        # 条目格式: "<mode> <type> <sha>\t<路径>"，只取 tree（子文件夹）
        if "\t" not in entry:
            continue
        meta, p = entry.split("\t", 1)
        fields = meta.split()
        if len(fields) < 2 or fields[1] != "tree":
            continue
        folder = p.rsplit("/", 1)[-1]
        chart_p = f"{prefix}/{folder}/chart/Chart.yaml"
        try:
            chart = yaml.safe_load(_run(["git", "-C", str(d), "show", f"{full}:{chart_p}"])) or {}
        except GitResolveError:
            continue                       # 没有 chart 的文件夹不是组件
        services: dict[str, str] = {}
        try:
            values = yaml.safe_load(_run(
                ["git", "-C", str(d), "show", f"{full}:{prefix}/{folder}/chart/values.yaml"])) or {}
            for svc, cfg in (values.get("services") or {}).items():
                port = (cfg or {}).get("port") if isinstance(cfg, dict) else None
                services[svc] = f"{svc}:{port}" if port else svc
        except GitResolveError:
            pass
        components.append({"name": folder, "release": chart.get("name") or folder,
                           "services": services})
    return {"path": prefix, "components": components}


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
