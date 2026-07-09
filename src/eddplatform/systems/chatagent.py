"""注册真实的 chatagent 被评系统（话痨说车 2.0 分布式 ↔ 2.3 单体）。

把真实的 System / SystemVersion / Dataset(用例) + **运行绑定**(前门 target/命名空间/评估器)
装进 store —— 这是系统的真实数据，评估服务据此对已部署在 k8s(edd-2-0 / edd-2-3)的两版本
跑真实前门评估。chatagent 的用例/评估器/前门适配器复用 ``examples/chatagent`` 里的定义。
"""

from __future__ import annotations

import sys
from pathlib import Path

# examples/ 在仓库根，加进 sys.path 以复用 chatagent 的真实用例/评估器/前门 target。
_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from eddplatform.api.store import RunBinding, Store  # noqa: E402
from eddplatform.domain.models import (  # noqa: E402
    Dataset,
    System,
    SystemVersion,
    VersionStatus,
)

SYSTEM_ID = "chatagent"
NAMESPACES = {"2.0": "edd-2-0", "2.3": "edd-2-3"}   # 版本 → 已部署的 k8s namespace


def register(store: Store) -> None:
    from examples.chatagent.cases import ALL_CASES
    from examples.chatagent.evaluators import all_evaluators
    from examples.chatagent.frontdoor import make_frontdoor_target

    store.add_system(System(
        id=SYSTEM_ID, name="话痨说车 chatagent", owner="AI 平台", prod_version="2.0"))

    store.add_version(SystemVersion(
        id="chatagent-2.0", system_id=SYSTEM_ID, label="2.0", status=VersionStatus.PRODUCTION,
        module_pins={"orchestrator": "2.0", "workflows": "2.0", "bma": "2.0",
                     "ca2-mainagent": "2.0", "toolprovider": "2.0"},
        note="旧：orchestrator → workflows → BMA(独立分类/路由) → chatagent2 collect + toolprovider（5 进程分布式）"))
    store.add_version(SystemVersion(
        id="chatagent-2.3", system_id=SYSTEM_ID, label="2.3", status=VersionStatus.DRAFT,
        module_pins={"orchestrator": "2.3", "mainagent": "2.3",
                     "sessionstore": "2.3", "toolexecutor": "2.3"},
        note="新：orchestrator → chatagent3 单 hlsc_agent（+ toolexecutor）；重构收敛为单体 agent"))

    store.set_dataset(Dataset(
        name="chatagent 三场景（guide / searchshops / searchcoupons）",
        system_id=SYSTEM_ID, cases=list(ALL_CASES)))

    from eddplatform.integrations import langfuse

    def _true_usage(session_id: str, n_turns: int) -> dict | None:
        """按 session 从 Langfuse 拉真实、完整的全链路 token（含 BMA/collect 下游）。
        Langfuse 不可达或未摄取到 → None，target 自动退回 SSE（少算但不阻断）。"""
        lf = langfuse.session_usage(session_id, expected_traces=n_turns)
        return langfuse.to_token_usage(lf) if lf.get("generations") else None

    def make_target(version_label: str):
        ns = NAMESPACES[version_label]
        return make_frontdoor_target(ns, orch="orchestrator", port=7100,
                                     turn_timeout=175, usage_lookup=_true_usage)

    store.register_binding(RunBinding(
        system_id=SYSTEM_ID, make_target=make_target,
        evaluators=all_evaluators(), namespaces=NAMESPACES))
