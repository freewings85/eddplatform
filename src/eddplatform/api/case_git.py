"""用例仓 git 双向同步：数据库是工作区，git 是版本仓。

- **导入（git → 库缓存）**：全量重建——拉分支最新 commit，扫描所有含 yaml 的
  文件夹（一个文件夹 = 一个用例库），解析后整体替换数据库缓存。不做逐条比对，
  "什么变了"由 git 历史回答。
- **导出（库 → git）**：把一个用例库写回它对应的文件夹——**一条用例一个
  YAML 文件**（`<id>.yaml`，git diff/PR 评审友好），先清空文件夹里的旧 yaml
  再写（全量规则），commit + push。
"""

from __future__ import annotations

import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

import yaml

from eddplatform.api import case_yaml
from eddplatform.api.git_resolve import GitResolveError, _mirror, _run
from eddplatform.domain.models import Case, DatasetInfo, System
from eddplatform.store.case_store import CaseStore
from eddplatform.store.dataset_store import DatasetStore

_GIT_ID = ["-c", "user.name=eddplatform", "-c", "user.email=edd@platform.local"]


def _require_repo(system: System) -> tuple[str, str]:
    if not system.cases_git_url:
        raise GitResolveError("该系统未配置用例仓库（系统编辑里填 git 地址）")
    return system.cases_git_url, system.cases_branch or "main"


def import_from_git(system: System, dataset_store: DatasetStore, case_store: CaseStore) -> dict:
    """全量导入：git 分支最新 → 发现库文件夹 → 解析 → 整体替换缓存。"""
    git_url, branch = _require_repo(system)
    d = _mirror(git_url)
    out = _run(["git", "ls-remote", git_url, f"refs/heads/{branch}"]).strip().splitlines()
    if not out:
        raise GitResolveError(f"用例仓里没有分支 {branch!r}")
    commit = out[0].split()[0]
    _run(["git", "-C", str(d), "fetch", "--prune", "--quiet"])

    files = _run(["git", "-C", str(d), "ls-tree", "-r", "--name-only", commit]).splitlines()
    by_folder: dict[str, list[str]] = defaultdict(list)
    for f in files:
        if f.endswith((".yaml", ".yml")):
            folder = str(Path(f).parent)
            by_folder[folder].append(f)

    existing = {ds.path: ds for ds in dataset_store.list(system.id) if ds.path}
    report: dict = {"commit": commit, "libraries": []}
    errors: list[str] = []
    for folder in sorted(by_folder):
        cases: list[Case] = []
        seen: set[str] = set()
        for f in sorted(by_folder[folder]):
            text = _run(["git", "-C", str(d), "show", f"{commit}:{f}"])
            try:
                for c in case_yaml.parse_eval_yaml(text):
                    if c.id in seen:
                        errors.append(f"{f}: 用例 id 重复 {c.id}（后者生效）")
                    seen.add(c.id)
                    cases.append(c)
            except ValueError as e:
                errors.append(f"{f}: {e}")
        if not cases:
            continue
        name = folder if folder != "." else "根目录用例库"
        if folder in existing:
            ds = existing.pop(folder)
            ds.name = name
            dataset_store.update(system.id, ds.id, ds)
        else:
            ds = dataset_store.create(system.id, DatasetInfo(
                name=name, path=folder, description=f"git 导入自 {folder}/"))
        case_store.import_cases(system.id, ds.id, cases, mode="replace")
        report["libraries"].append({"id": ds.id, "path": folder, "count": len(cases)})

    # git 里消失的（曾经 git 导入的）库整库删除——全量规则
    for gone in existing.values():
        case_store.import_cases(system.id, gone.id, [], mode="replace")
        dataset_store.delete(system.id, gone.id)
        report["libraries"].append({"id": gone.id, "path": gone.path, "count": 0, "removed": True})
    if errors:
        report["errors"] = errors
    return report


def export_to_git(system: System, dataset: DatasetInfo, cases: list[Case]) -> dict:
    """把一个用例库写回 git：一条用例一个文件，清空旧 yaml 后重写，commit+push。"""
    git_url, branch = _require_repo(system)
    folder = dataset.path or dataset.name
    with tempfile.TemporaryDirectory(prefix="edd-cases-") as tmp:
        work = Path(tmp) / "repo"
        _run(["git", "clone", "--quiet", "--branch", branch, "--single-branch",
              git_url, str(work)])
        target = work / folder
        target.mkdir(parents=True, exist_ok=True)
        for old in list(target.glob("*.yaml")) + list(target.glob("*.yml")):
            old.unlink()
        for c in cases:
            doc = case_yaml.case_to_yaml_doc(c)
            (target / f"{c.id}.yaml").write_text(
                yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
        _run(["git", "-C", str(work), "add", "-A"])
        status = _run(["git", "-C", str(work), "status", "--porcelain"]).strip()
        if not status:
            head = _run(["git", "-C", str(work), "rev-parse", "HEAD"]).strip()
            return {"commit": head, "files": len(cases), "changed": False}
        msg = f"edd: 导出用例库 {dataset.name}（{len(cases)} 条）"
        _run(["git", *_GIT_ID, "-C", str(work), "commit", "-qm", msg])
        try:
            _run(["git", "-C", str(work), "push", "--quiet", "origin", branch])
        except GitResolveError as e:
            raise GitResolveError(f"push 失败（远端可能有新提交，先「从 git 导入」再导出）: {e}")
        commit = _run(["git", "-C", str(work), "rev-parse", "HEAD"]).strip()
    # 导出后 path 固化（本地新建库首次导出时补上）
    if not dataset.path:
        dataset.path = folder
    return {"commit": commit, "files": len(cases), "changed": True}


def _git_commit_env_ok() -> bool:  # pragma: no cover —— 供将来健康检查用
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except Exception:  # noqa: BLE001
        return False
