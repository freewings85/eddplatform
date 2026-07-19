"""仓库约定 ``.eddplatform.yaml`` 的解析。

一个「被测系统」或「评估程序」的仓库，根目录放一个 ``.eddplatform.yaml``：

    apiVersion: eddplatform/v1
    kind: system            # system | eval
    build: ./build.sh       # 构建脚本：产出镜像 tar + images.json 到 $EDD_OUT_DIR
    chart: ./deploy/chart   # helm chart 路径
    services: [quote, gateway]

平台据此拉代码 → 跑 build → helm 部署，全程不用把版本埋进自由脚本。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONVENTION_FILE = ".eddplatform.yaml"


@dataclass
class RepoSpec:
    kind: str                          # system | eval
    build: str                         # 构建脚本相对路径
    chart: str                         # helm chart 相对路径
    services: list[str] = field(default_factory=list)
    api_version: str = "eddplatform/v1"


def read_repo_spec(repo_dir: str | Path) -> RepoSpec:
    """从仓库根读 .eddplatform.yaml；缺文件/缺必填字段直接报错。"""
    path = Path(repo_dir) / CONVENTION_FILE
    if not path.exists():
        raise FileNotFoundError(f"仓库缺少约定文件 {CONVENTION_FILE}: {path}")
    data = yaml.safe_load(path.read_text()) or {}
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
