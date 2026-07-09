"""进程内领域数据存储 —— 取代占位 sample_data，承载**真实**评估数据。

API 读写同一个 ``STORE`` 单例；评估服务(evals.service)把真实 run/评估结果写进来，
API 端点从这里读。系统版本怎么"跑"(前门 target/命名空间/运行期评估器)由 ``RunBinding``
注册进来——这部分是代码、不走序列化，不对外暴露。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from eddplatform.domain.models import (
    Dataset,
    Environment,
    EvaluatorDef,
    Evaluation,
    Requirement,
    RunRecord,
    SandboxConfig,
    System,
    SystemVersion,
)


@dataclass
class RunBinding:
    """一个系统"怎么真实跑评估"的绑定：给版本 → 造 target；运行期评估器；版本→命名空间。"""

    system_id: str
    make_target: Callable[[str], Callable[[Any], Any]]   # version_label -> target(inputs)
    evaluators: dict[str, Any]                            # name -> Evaluator(运行期对象)
    namespaces: dict[str, str] = field(default_factory=dict)   # version_label -> k8s namespace


class Store:
    def __init__(self) -> None:
        self.systems: list[System] = []
        self.versions: list[SystemVersion] = []
        self.datasets: dict[str, Dataset] = {}
        self.requirements: list[Requirement] = []
        self.evaluator_defs: dict[str, list[EvaluatorDef]] = {}
        self.sandbox_configs: list[SandboxConfig] = []
        self.environments: list[Environment] = []
        self.runs: list[RunRecord] = []
        self.evaluations: list[Evaluation] = []
        self.bindings: dict[str, RunBinding] = {}
        self._run_seq = 0
        self._eval_seq = 0

    # ── id 分配 ──
    def next_run_id(self) -> str:
        self._run_seq += 1
        return f"R-{1000 + self._run_seq}"

    def next_eval_id(self) -> str:
        self._eval_seq += 1
        return f"E-{3000 + self._eval_seq}"

    # ── 系统 / 版本 / 用例集 ──
    def add_system(self, s: System) -> System:
        self.systems.append(s)
        return s

    def system_by_id(self, sid: str) -> System | None:
        return next((s for s in self.systems if s.id == sid), None)

    def add_version(self, v: SystemVersion) -> SystemVersion:
        self.versions.append(v)
        return v

    def versions_for(self, sid: str) -> list[SystemVersion]:
        return [v for v in self.versions if v.system_id == sid]

    def set_dataset(self, ds: Dataset) -> Dataset:
        self.datasets[ds.system_id] = ds
        return ds

    def dataset_for(self, sid: str) -> Dataset | None:
        return self.datasets.get(sid)

    # ── 需求 / 评估器定义 / 沙箱 / 环境 ──
    def requirements_for(self, sid: str) -> list[Requirement]:
        return [r for r in self.requirements if r.system_id == sid]

    def requirement_by_id(self, rid: str) -> Requirement | None:
        return next((r for r in self.requirements if r.id == rid), None)

    def add_requirement(self, r: Requirement) -> Requirement:
        self.requirements.append(r)
        return r

    def evaluators_for(self, sid: str) -> list[EvaluatorDef]:
        return self.evaluator_defs.get(sid, [])

    # ── 运行 / 评估 ──
    def add_run(self, r: RunRecord) -> RunRecord:
        self.runs.append(r)
        return r

    def run_by_id(self, rid: str) -> RunRecord | None:
        return next((r for r in self.runs if r.id == rid), None)

    def add_evaluation(self, e: Evaluation) -> Evaluation:
        self.evaluations.append(e)
        return e

    def eval_by_id(self, eid: str) -> Evaluation | None:
        return next((e for e in self.evaluations if e.id == eid), None)

    def completed_evaluations(self, sid: str) -> list[Evaluation]:
        from eddplatform.domain.models import EvalStatus
        return [e for e in self.evaluations
                if e.system_id == sid and e.status == EvalStatus.COMPLETED and e.result]

    # ── 运行绑定(代码，不序列化) ──
    def register_binding(self, b: RunBinding) -> None:
        self.bindings[b.system_id] = b


STORE = Store()
