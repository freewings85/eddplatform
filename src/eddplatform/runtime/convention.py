"""仓库约定 ``.eddplatform.yaml`` 的解析。

**可部署单元 = 仓库里的一个文件夹**（默认 ``.`` = 仓库根）。单元目录里放一个
``.eddplatform.yaml``，``build``/``chart`` 路径相对该目录：

    apiVersion: eddplatform/v1
    kind: system            # system | eval
    build: ./build.sh       # 构建脚本：产出镜像 tar + images.json 到 $EDD_OUT_DIR
    chart: ./deploy/chart   # helm chart 路径
    services: [quote, gateway]

一个仓库可以有多个单元（如 chatagent 仓：``edd/system`` 放被评系统、``edd/eval``
放评估程序），平台按「git 仓库 + ref + 目录」定位一个单元：拉代码 → 跑 build →
helm 部署，全程不用把版本埋进自由脚本。完整规范见
``docs/EDD接入约定_被评系统与评估程序.md``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONVENTION_FILE = ".eddplatform.yaml"


@dataclass
class RepoSpec:
    kind: str                          # system | eval
    build: str                         # 构建脚本相对路径（相对单元目录）
    chart: str                         # helm chart 相对路径（相对单元目录）
    services: list[str] = field(default_factory=list)
    api_version: str = "eddplatform/v1"


def read_repo_spec(repo_dir: str | Path, path: str = ".") -> RepoSpec:
    """从仓库的单元目录（``repo_dir/path``）读 .eddplatform.yaml；缺文件/缺必填字段直接报错。"""
    unit = Path(repo_dir) / path
    file = unit / CONVENTION_FILE
    if not file.exists():
        raise FileNotFoundError(f"单元目录缺少约定文件 {CONVENTION_FILE}: {file}")
    data = yaml.safe_load(file.read_text()) or {}
    missing = [k for k in ("kind", "build", "chart") if not data.get(k)]
    if missing:
        raise ValueError(f"{CONVENTION_FILE} 缺少必填字段: {', '.join(missing)}")
    if data["kind"] not in ("system", "eval"):
        raise ValueError(f"kind 必须是 system 或 eval，得到 {data['kind']!r}")
    return RepoSpec(
        kind=data["kind"],
        build=data["build"],
        chart=data["chart"],
        services=list(data.get("services", [])),
        api_version=data.get("apiVersion", "eddplatform/v1"),
    )
