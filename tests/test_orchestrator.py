"""前置条件编排测试：顺序、版本结构化标签、失败中止——用假部署器，不依赖 k8s。"""

import pytest

from eddplatform.domain.models import Precondition, PreconditionKind
from eddplatform.runtime import Orchestrator
from eddplatform.runtime.deployer import DeployResult


class FakeDeployer:
    """记录 deploy 调用；返回 ref 原样，供断言版本标签。"""

    kubeconfig = "fake"

    def __init__(self):
        self.deployed = []

    def deploy(self, *, git_url, ref, release, namespace, path="."):
        self.deployed.append((release, ref))
        return DeployResult(
            release=release, namespace=namespace, ref=ref, image_tag=ref[:12],
            images={"svc": f"img:{ref[:12]}"}, pods=[f"{release}-x Running"],
        )

    def uninstall(self, *, release, namespace):
        pass

    def delete_namespace(self, namespace):
        pass


def _orch():
    return Orchestrator(FakeDeployer(), log=lambda m: None)


def test_brings_up_both_subjects_with_version_labels():
    pcs = [
        Precondition(kind=PreconditionKind.START_SYSTEM, name="sys",
                     git_url="file://sys", commit="aaaa1111"),
        Precondition(kind=PreconditionKind.START_EVAL_PROGRAM, name="eval",
                     git_url="file://eval", commit="bbbb2222"),
    ]
    env = _orch().bring_up(pcs, "ns1")
    assert env.status == "up"
    assert env.versions == {"sys": "aaaa1111", "eval": "bbbb2222"}
    assert env.releases == ["sys", "eval"]
    assert [o.status for o in env.outcomes] == ["ok", "ok"]


def test_custom_script_runs_in_order():
    pcs = [
        Precondition(kind=PreconditionKind.START_SYSTEM, name="sys",
                     git_url="file://sys", commit="aaaa"),
        Precondition(kind=PreconditionKind.CUSTOM_SCRIPT, name="seed", script="true"),
    ]
    env = _orch().bring_up(pcs, "ns2")
    assert env.status == "up"
    assert env.outcomes[-1].kind == "custom_script"


def test_failure_aborts_subsequent_preconditions():
    pcs = [
        Precondition(kind=PreconditionKind.START_SYSTEM, name="sys",
                     git_url="file://sys", commit="aaaa"),
        Precondition(kind=PreconditionKind.CUSTOM_SCRIPT, name="bad", script="exit 3"),
        Precondition(kind=PreconditionKind.START_EVAL_PROGRAM, name="eval",
                     git_url="file://eval", commit="bbbb"),
    ]
    env = _orch().bring_up(pcs, "ns3")
    assert env.status == "failed"
    kinds = [o.kind for o in env.outcomes]
    assert kinds == ["start_system", "custom_script"]   # eval 没被执行
    assert env.outcomes[-1].status == "failed"
    assert "eval" not in env.versions


def test_missing_ref_is_a_failure():
    pcs = [Precondition(kind=PreconditionKind.START_SYSTEM, name="sys", git_url="file://sys")]
    env = _orch().bring_up(pcs, "ns4")
    assert env.status == "failed"
    assert env.outcomes[0].status == "failed"


@pytest.mark.parametrize("script,ok", [("true", True), ("false", False)])
def test_custom_script_status(script, ok):
    pcs = [Precondition(kind=PreconditionKind.CUSTOM_SCRIPT, name="s", script=script)]
    env = _orch().bring_up(pcs, "ns5")
    assert (env.status == "up") is ok
