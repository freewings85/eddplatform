"""可部署单元约定：**标准 helm chart + 一个构建脚本**，没有自有清单文件。

单元目录（仓库里任意文件夹，默认 ``.`` = 仓库根）必须包含::

    build.sh   构建脚本：吃 $EDD_IMAGE_TAG / $EDD_OUT_DIR，产镜像 tar + images.json
    chart/     标准 helm chart：
               - Chart.yaml 的 ``name`` = helm release 名（部署实例标识）
               - values.yaml 的 ``services.<服务名>.image`` = 镜像注入挂点；
                 服务名 = k8s Service DNS 名（集群内互相调用的地址）

一个仓库可以有多个单元（如 chatagent 仓：``edd/mainagent``、``edd/eval`` 各一个），
平台按「git 仓库 + ref + 目录」定位单元：拉代码 → 跑 build → helm 部署。
完整规范见 ``docs/EDD接入约定_被评系统与评估程序.md`` 与可下载的 edd_helm 示例。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

BUILD_SCRIPT = "build.sh"
CHART_DIR = "chart"
_NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass
class UnitSpec:
    name: str                          # helm release 名（来自 chart/Chart.yaml 的 name）
    services: list[str] = field(default_factory=list)   # values.yaml services 的键


def read_unit(repo_dir: str | Path, path: str = ".") -> UnitSpec:
    """从仓库的单元目录（``repo_dir/path``）读单元信息；不满足约定直接报错。"""
    unit = Path(repo_dir) / path
    build = unit / BUILD_SCRIPT
    chart_yaml = unit / CHART_DIR / "Chart.yaml"
    if not build.exists():
        raise FileNotFoundError(f"单元缺少构建脚本: {build}")
    if not chart_yaml.exists():
        raise FileNotFoundError(f"单元缺少 helm chart: {chart_yaml}")
    chart = yaml.safe_load(chart_yaml.read_text()) or {}
    name = chart.get("name")
    if not name or not _NAME_RE.fullmatch(str(name)):
        raise ValueError(
            f"chart/Chart.yaml 的 name 无效（作 helm release 名，需小写字母/数字/中划线）: {name!r}")
    services: list[str] = []
    values_file = unit / CHART_DIR / "values.yaml"
    if values_file.exists():
        values = yaml.safe_load(values_file.read_text()) or {}
        services = list((values.get("services") or {}).keys())
    return UnitSpec(name=str(name), services=services)
