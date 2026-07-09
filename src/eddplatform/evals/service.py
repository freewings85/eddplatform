"""评估服务 —— 让 EDD **系统自己**跑一次真实评估并落库。

流程：``start_evaluation`` 先建一条 RUNNING 的 RunRecord + Evaluation（前端立刻能看到"运行中"），
后台线程 ``execute`` 用系统注册的 ``RunBinding`` 造前门 target → ``engine.run`` 打**真实环境**
（如 k8s 里已部署的版本）→ 把 EvalResult 写回，状态置 COMPLETED。两条评估交给 ``comparison_of``
调 ``engine.compare`` 出老新对比。全程走系统的领域模型 + store + 引擎，不是外挂脚本。
"""

from __future__ import annotations

import threading
import time

from eddplatform.api.store import Store
from eddplatform.domain.models import (
    Comparison,
    EvalStatus,
    Evaluation,
    RunRecord,
    RunStatus,
    RunType,
)
from eddplatform.evals.engine import compare as engine_compare
from eddplatform.evals.engine import run as engine_run

# 跑评估时附加到每条用例的维度评估器：让 metrics 自动带上 时延/token/缓存分账，
# 从而 compare() 能产出这些维度的老新 delta（仅统计 binding.evaluators 里真实存在的）。
DIM_EVALUATORS = [
    "维度-时延s", "维度-成本token", "维度-input_token",
    "维度-缓存token", "维度-非缓存token", "维度-缓存命中率",
]


def create_pending(store: Store, system_id: str, version_label: str) -> tuple[RunRecord, Evaluation]:
    """建 RUNNING 占位的 RunRecord + Evaluation 并落 store，立即返回（供前端显示运行中）。"""
    binding = store.bindings.get(system_id)
    ns = binding.namespaces.get(version_label) if binding else None
    ds = store.dataset_for(system_id)
    run = RunRecord(id=store.next_run_id(), type=RunType.EVALUATION, system_id=system_id,
                    version_label=version_label, environment_id=ns, status=RunStatus.RUNNING)
    ev = Evaluation(id=store.next_eval_id(), name=f"{system_id} · {version_label} 评估",
                    system_id=system_id, version_label=version_label,
                    dataset_name=ds.name if ds else "", sandbox_config="k8s-ephemeral",
                    run_id=run.id, status=EvalStatus.RUNNING)
    run.eval_id = ev.id
    store.add_run(run)
    store.add_evaluation(ev)
    return run, ev


def execute(store: Store, run: RunRecord, ev: Evaluation) -> Evaluation:
    """真正跑：造 target → engine.run（打真实环境）→ 写回结果 + 状态。异常置 FAILED 并抛出。"""
    binding = store.bindings[ev.system_id]
    ds = store.dataset_for(ev.system_id)
    cases = [
        c.model_copy(update={"evaluator_names": list(dict.fromkeys(c.evaluator_names + DIM_EVALUATORS))})
        for c in (ds.cases if ds else [])
        if c.enabled and c.applies_to(ev.version_label)
    ]
    t0 = time.perf_counter()
    try:
        target = binding.make_target(ev.version_label)
        result = engine_run(target, cases, binding.evaluators)
    except Exception:
        run.duration_s = round(time.perf_counter() - t0, 1)
        run.status = RunStatus.FAILED
        ev.status = EvalStatus.FAILED
        raise
    run.duration_s = round(time.perf_counter() - t0, 1)
    run.status = RunStatus.COMPLETED
    ev.result = result
    ev.status = EvalStatus.COMPLETED
    return ev


def start_evaluation(store: Store, system_id: str, version_label: str,
                     *, background: bool = True) -> tuple[RunRecord, Evaluation]:
    """触发一次评估。background=True → 后台线程跑（端点立即返回 RUNNING 的 id）。"""
    run, ev = create_pending(store, system_id, version_label)
    if background:
        threading.Thread(target=_safe_execute, args=(store, run, ev), daemon=True).start()
    else:
        _safe_execute(store, run, ev)   # 同步也吞异常：状态(FAILED/COMPLETED)即权威结果
    return run, ev


def _safe_execute(store: Store, run: RunRecord, ev: Evaluation) -> None:
    try:
        execute(store, run, ev)
    except Exception:
        pass  # 状态已在 execute 内置 FAILED


def comparison_of(store: Store, baseline_eval_id: str, candidate_eval_id: str) -> Comparison | None:
    """两条已完成评估 → engine.compare 出对比（填好 eval id）。任一缺结果 → None。"""
    b = store.eval_by_id(baseline_eval_id)
    c = store.eval_by_id(candidate_eval_id)
    if not (b and c and b.result and c.result):
        return None
    cmp = engine_compare(b.result, c.result)
    cmp.baseline_eval_id = b.id
    cmp.candidate_eval_id = c.id
    return cmp
