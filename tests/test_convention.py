"""仓库约定 .eddplatform.yaml 解析测试（纯逻辑，不依赖 k8s/helm）。"""

from pathlib import Path

import pytest

from eddplatform.runtime import read_repo_spec

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-system"


def _write(tmp_path, text: str) -> Path:
    (tmp_path / ".eddplatform.yaml").write_text(text)
    return tmp_path


def test_parse_valid(tmp_path):
    repo = _write(tmp_path, """
apiVersion: eddplatform/v1
kind: system
build: ./build.sh
chart: ./deploy/chart
services: [quote, gateway]
""")
    spec = read_repo_spec(repo)
    assert spec.kind == "system"
    assert spec.build == "./build.sh"
    assert spec.chart == "./deploy/chart"
    assert spec.services == ["quote", "gateway"]


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_repo_spec(tmp_path)


def test_missing_required_field_raises(tmp_path):
    repo = _write(tmp_path, "kind: system\nbuild: ./b.sh\n")  # 缺 chart
    with pytest.raises(ValueError):
        read_repo_spec(repo)


def test_bad_kind_raises(tmp_path):
    repo = _write(tmp_path, "kind: nonsense\nbuild: ./b.sh\nchart: ./c\n")
    with pytest.raises(ValueError):
        read_repo_spec(repo)


def test_real_demo_system_repo_parses():
    """随仓库附带的 examples/demo-system 必须符合约定。"""
    spec = read_repo_spec(DEMO)
    assert spec.kind == "system"
    assert spec.services == ["quote", "gateway"]
    assert (DEMO / spec.build).exists()
    assert (DEMO / spec.chart / "Chart.yaml").exists()


def test_unit_folder_convention(tmp_path):
    """一个仓库可含多个可部署单元：约定文件在单元目录里，路径相对单元目录。"""
    unit = tmp_path / "edd" / "eval"
    unit.mkdir(parents=True)
    (unit / ".eddplatform.yaml").write_text("""
apiVersion: eddplatform/v1
kind: eval
build: ./build.sh
chart: ./chart
""")
    spec = read_repo_spec(tmp_path, path="edd/eval")
    assert spec.kind == "eval" and spec.build == "./build.sh"


def test_unit_folder_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_repo_spec(tmp_path, path="edd/nope")
