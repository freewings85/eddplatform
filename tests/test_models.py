"""领域模型的核心不变量测试。"""

import pytest

from eddplatform.domain.models import Case, EvalProgram, RunRecord, RunStatus


def test_case_is_pure_registry_record():
    """用例=纯注册记录：没有评估内容字段（inputs/expect/code 都在评估代码仓）。"""
    c = Case(name="guide_platform_intro", description="平台介绍准确", tags=["group/guide"])
    assert not hasattr(c, "inputs")
    assert not hasattr(c, "expected_output")
    assert not hasattr(c, "code")


def test_case_name_rejects_whitespace():
    """name 是传给评估代码的标识——不允许空白。"""
    with pytest.raises(ValueError):
        Case(name="有 空格")
    with pytest.raises(ValueError):
        Case(name="   ")
    assert Case(name="  ok_name  ").name == "ok_name"


def test_eval_program_defaults():
    """评估程序注册项不含 workflow 名——那写在程序自己的代码/配置里。"""
    ep = EvalProgram(id="ep1", system_id="s", name="评估程序", git_url="/repo")
    assert ep.path == "."
    assert not hasattr(ep, "code")


def test_run_record_shape():
    r = RunRecord(system_id="s", task_id="t")
    assert r.status == RunStatus.RUNNING and r.outcomes == []
