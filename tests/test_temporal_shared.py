"""Temporal 入参映射测试（纯数据类，不需要 Temporal server）。"""

from eddplatform.domain.models import Precondition, PreconditionKind
from eddplatform.runtime.temporal import PreconditionSpec, RunTaskInput, to_spec


def test_to_spec_maps_domain_precondition():
    pc = Precondition(kind=PreconditionKind.START_SYSTEM, name="sys",
                      git_url="file://x", branch="2.3-eval", commit="abc123")
    spec = to_spec(pc)
    assert isinstance(spec, PreconditionSpec)
    assert spec.kind == "start_system"          # enum -> 字符串
    # 部署 ref 用固化的 commit（钉死可复现）
    assert (spec.name, spec.git_url, spec.ref) == ("sys", "file://x", "abc123")


def test_to_spec_falls_back_to_branch_without_commit():
    pc = Precondition(kind=PreconditionKind.START_SYSTEM, git_url="u", branch="main")
    assert to_spec(pc).ref == "main"


def test_to_spec_defaults_name_to_kind():
    pc = Precondition(kind=PreconditionKind.CUSTOM_SCRIPT, script="true")
    assert to_spec(pc).name == "custom_script"


def test_run_task_input_holds_ordered_specs():
    inp = RunTaskInput(
        preconditions=[
            to_spec(Precondition(kind=PreconditionKind.START_SYSTEM, name="s",
                                 git_url="u", commit="r")),
            to_spec(Precondition(kind=PreconditionKind.START_EVAL_PROGRAM, name="e",
                                 git_url="u2", commit="r2")),
        ],
        namespace="ns", eval_deploy="judge", eval_target="quote",
    )
    assert [p.kind for p in inp.preconditions] == ["start_system", "start_eval_program"]
    assert inp.eval_target == "quote"
