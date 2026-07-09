"""评估服务 TDD：通过系统跑一个版本 → 落 RunRecord + Evaluation；两评估 → Comparison。

用 stub target/evaluators（不碰 k8s），验证服务把结果落进 store 且状态流转正确。
"""
import sys

sys.path.insert(0, "src")

from eddplatform.api.store import RunBinding, Store  # noqa: E402
from eddplatform.domain.models import (  # noqa: E402
    Case,
    Dataset,
    EvalStatus,
    OutputType,
    RunStatus,
)
from eddplatform.evals.engine import Outcome  # noqa: E402
from eddplatform.evals import service  # noqa: E402


class _PassCheck:
    name = "断言-通过"

    def evaluate(self, ctx):
        ok = bool(ctx.output.get("ok", True))
        return Outcome(self.name, OutputType.ASSERTION, ok, ok, "")


class _Latency:
    name = "维度-时延s"

    def evaluate(self, ctx):
        v = float(ctx.output.get("latency_s", 0))
        return Outcome(self.name, OutputType.SCORE, v, True, "")


def _store_with(system_id, outputs_by_version):
    """构造一个注册好 binding + dataset 的 store。outputs_by_version[v] = 每条用例的 output。"""
    store = Store()
    cases = [Case(id="c1", name="用例1", inputs={"turns": [{"user": "hi"}]},
                  evaluator_names=["断言-通过"]),
             Case(id="c2", name="用例2", inputs={"turns": [{"user": "yo"}]},
                  evaluator_names=["断言-通过"])]
    store.set_dataset(Dataset(name="ds", system_id=system_id, cases=cases))

    def make_target(version):
        out = outputs_by_version[version]
        return lambda inputs: dict(out)

    store.register_binding(RunBinding(
        system_id=system_id, make_target=make_target,
        evaluators={"断言-通过": _PassCheck(), "维度-时延s": _Latency()},
        namespaces={"2.0": "edd-2-0", "2.3": "edd-2-3"}))
    return store


def test_evaluate_version_persists_completed_run_and_evaluation():
    store = _store_with("sys", {"2.0": {"ok": True, "latency_s": 1.5}})
    run, ev = service.start_evaluation(store, "sys", "2.0", background=False)

    assert store.run_by_id(run.id).status == RunStatus.COMPLETED
    assert store.run_by_id(run.id).environment_id == "edd-2-0"
    ev2 = store.eval_by_id(ev.id)
    assert ev2.status == EvalStatus.COMPLETED
    assert ev2.run_id == run.id
    assert ev2.result is not None
    assert ev2.result.pass_rate == 1.0                       # 两条都通过
    assert ev2.result.metrics["维度-时延s"] == 1.5           # 维度均值落进 metrics
    assert len(ev2.result.case_results) == 2


def test_failed_target_marks_run_and_eval_failed():
    store = _store_with("sys", {"2.0": {}})

    def boom(version):
        def _t(inputs):
            raise RuntimeError("k8s down")
        return _t
    store.bindings["sys"].make_target = boom

    run, ev = service.start_evaluation(store, "sys", "2.0", background=False)
    assert store.run_by_id(run.id).status == RunStatus.FAILED
    assert store.eval_by_id(ev.id).status == EvalStatus.FAILED


def test_comparison_of_two_evaluations_fills_ids_and_counts():
    # 2.0 用例2 挂了；2.3 都过 → improved 计到那条翻转
    store = _store_with("sys", {"2.0": {"ok": True}, "2.3": {"ok": True}})
    # 让 2.0 的 c2 失败：用一个按 case 变化的 target
    seq = {"n": 0}

    def make_target(version):
        def _t(inputs):
            if version == "2.0" and inputs["turns"][0]["user"] == "yo":
                return {"ok": False}
            return {"ok": True}
        return _t
    store.bindings["sys"].make_target = make_target

    _, ev_a = service.start_evaluation(store, "sys", "2.0", background=False)
    _, ev_b = service.start_evaluation(store, "sys", "2.3", background=False)

    cmp = service.comparison_of(store, ev_a.id, ev_b.id)
    assert cmp is not None
    assert cmp.baseline_eval_id == ev_a.id
    assert cmp.candidate_eval_id == ev_b.id
    assert cmp.applicable_cases == 2
    assert cmp.improved == 1        # c2: 2.0 fail → 2.3 pass
    assert cmp.regressed == 0
    # 通过率 delta 在 metrics 里
    names = [m.metric for m in cmp.metrics]
    assert "通过率" in names


def test_comparison_none_when_result_missing():
    store = _store_with("sys", {"2.0": {"ok": True}})
    _, ev_a = service.start_evaluation(store, "sys", "2.0", background=False)
    # 造一个没有 result 的评估 id
    assert service.comparison_of(store, ev_a.id, "E-nope") is None
