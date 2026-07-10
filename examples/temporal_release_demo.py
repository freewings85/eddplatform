"""Temporal live demo：连本地 docker Temporal server（deploy/temporal/），用 MockProvider
端到端跑一轮发布评估，结果与纯 Python 版一致。集群在时可把 MockProvider 换成 K8sProvider。

先决：docker compose up -d（deploy/temporal/）+ pip install -e '.[temporal]'。
本模块 import-safe：真正执行在 __main__ 守卫下。
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

# 复用 tests/ 里的确定性样例（本 demo 只演示 live 编排，不重复造数据）。运行
# `python examples/temporal_release_demo.py` 时 tests/ 不在 sys.path → 手动加入。
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tests"))

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from eddplatform.orchestration import temporal_workflow as tw
from eddplatform.orchestration.providers import MockProvider
from release_sample import (  # noqa: E402  (须在上面的 sys.path 插入之后导入)
    DATASET, EVALUATORS, MODULES, REQUIREMENTS, V1, V2, target_factory,
)

TEMPORAL_ADDRESS = "localhost:7233"


def build_request() -> "tw.ReleaseEvalRequest":
    return tw.ReleaseEvalRequest(baseline_version=V1, candidate_version=V2,
                                 dataset=DATASET, requirements=REQUIREMENTS)


async def main() -> None:
    client = await Client.connect(TEMPORAL_ADDRESS, data_converter=pydantic_data_converter)
    res = await tw.run_release_evaluation_via_temporal(
        client, request=build_request(), provider=MockProvider(),
        target_factory=target_factory, evaluators=EVALUATORS, modules=MODULES)
    c = res.comparison
    print(f"改善 {c.improved} / 回归 {c.regressed} / 持平 {c.unchanged} / 共有 {c.applicable_cases}")
    for r in c.by_requirement:
        print(f"  需求 {r.requirement_id} {r.title}: {r.baseline_passed}→{r.candidate_passed} "
              f"（{r.verdict}）")


if __name__ == "__main__":
    asyncio.run(main())
