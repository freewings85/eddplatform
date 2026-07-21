"""可部署单元约定解析测试：标准 helm chart + build.sh（纯逻辑，不依赖 k8s/helm）。"""

from pathlib import Path

import pytest

from eddplatform.runtime import read_unit

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo-system"


def _write_unit(root: Path, name="demo", services=("web",)) -> Path:
    (root / "chart").mkdir(parents=True, exist_ok=True)
    (root / "build.sh").write_text("#!/bin/bash\ntrue\n")
    (root / "chart" / "Chart.yaml").write_text(f"apiVersion: v2\nname: {name}\nversion: 0.1.0\n")
    svc = "\n".join(f"  {s}:\n    image: \"\"\n    port: 80" for s in services)
    (root / "chart" / "values.yaml").write_text(f"services:\n{svc}\n")
    return root


def test_read_unit_from_standard_chart(tmp_path):
    _write_unit(tmp_path, name="mainagent", services=("mainagent", "sessionstore"))
    spec = read_unit(tmp_path)
    assert spec.name == "mainagent"
    assert spec.services == ["mainagent", "sessionstore"]


def test_unit_folder_convention(tmp_path):
    """一个仓库可含多个单元：按目录定位。"""
    _write_unit(tmp_path / "edd" / "eval", name="eval-demo")
    spec = read_unit(tmp_path, path="edd/eval")
    assert spec.name == "eval-demo"


def test_missing_build_script_means_pure_chart_unit(tmp_path):
    """无 build.sh = 纯 chart 单元（基础组件）：不报错，标记 has_build=False。"""
    _write_unit(tmp_path)
    (tmp_path / "build.sh").unlink()
    spec = read_unit(tmp_path)
    assert spec.has_build is False
    assert spec.name


def test_regular_unit_has_build(tmp_path):
    _write_unit(tmp_path)
    assert read_unit(tmp_path).has_build is True


def test_missing_chart_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_unit(tmp_path)


def test_invalid_chart_name_raises(tmp_path):
    _write_unit(tmp_path, name="Bad Name")
    with pytest.raises(ValueError):
        read_unit(tmp_path)


def test_demo_system_repo_satisfies_convention():
    """仓内 demo-system 示例必须满足约定（防示例烂掉）。"""
    spec = read_unit(DEMO)
    assert spec.name == "demo-system"
    assert set(spec.services) == {"quote", "gateway"}


def test_parse_env_lines():
    from eddplatform.runtime.deployer import _parse_env
    text = "LITELLM_KEY=sk-x\n# 注释\n\nFOO=bar=baz\n 空格KEY = v \nBAD_LINE\n"
    assert _parse_env(text) == {"LITELLM_KEY": "sk-x", "FOO": "bar=baz", "空格KEY": "v"}
    assert _parse_env(None) == {} and _parse_env("") == {}
