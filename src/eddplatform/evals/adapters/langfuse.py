"""评估引擎（推荐、主干）：Langfuse —— 复用优秀开源，不自研。

Langfuse 负责：dataset / experiment(dataset run)、评估器打分(score)、
**baseline vs candidate 并排对比**、OTel 追踪。EddPlatform 只做薄胶水：
把系统入口(system)按用例跑一遍 → run_experiment 自动建 dataset run + 打分 →
到 Langfuse Compare 看老新对比。

需要一个 Langfuse 实例 + 环境变量：
    LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
本地自托管见 deploy/langfuse/（docker compose up -d）。安装：pip install -e '.[langfuse]'

按 langfuse SDK v4 编写（run_experiment / create_dataset_item / create_score）。
"""

from __future__ import annotations

from typing import Any, Callable

from eddplatform.domain.models import Dataset as DomainDataset

# v4 评估器函数：evaluator(*, input, output, expected_output, metadata, **kwargs)
#                → 返回 {"name","value","comment"?} 或其列表；value 为 bool/数值/字符串
Evaluator = Callable[..., Any]
System = Callable[[Any], Any]  # 被评系统入口：input -> output（黑盒）


def available() -> bool:
    try:
        import langfuse  # noqa: F401

        return True
    except ImportError:
        return False


def _client():
    if not available():
        raise RuntimeError(
            "该引擎需要 Langfuse：pip install -e '.[langfuse]'，"
            "并设置 LANGFUSE_HOST / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY。"
        )
    from langfuse import Langfuse

    return Langfuse()  # 从环境变量读 host / keys


def sync_dataset(dataset: DomainDataset) -> None:
    """把用例集推到 Langfuse dataset（可维护、可作为发布评估的输入）。可重复执行(按 id upsert)。"""
    lf = _client()
    lf.create_dataset(name=dataset.name)
    for c in dataset.cases:
        lf.create_dataset_item(
            dataset_name=dataset.name,
            id=c.id,
            input=c.inputs,
            expected_output=c.expected_output,
            metadata={
                **c.metadata,
                "case_version": c.case_version,
                "applicable_versions": c.applicable_versions,
            },
        )
    lf.flush()


def run_version(dataset_name: str, run_name: str, system: System, evaluators: list[Evaluator]):
    """对某个系统版本跑一次 dataset run：run_experiment 自动追踪 + 打分 + 建 run。

    ``run_name`` 建议用系统版本标识（如 ``insurance-v1`` / ``insurance-v2``），
    两个 run 即可在 Langfuse Compare 视图作 baseline vs candidate 对比。
    """
    lf = _client()
    dataset = lf.get_dataset(dataset_name)

    def task(*, item, **_kwargs):  # v4 任务签名：task(*, item)
        return system(item.input)

    result = lf.run_experiment(
        name=run_name, run_name=run_name, data=dataset.items, task=task, evaluators=evaluators
    )
    lf.flush()
    return result


def delete_run(dataset_name: str, run_name: str) -> None:
    """删掉同名 dataset run（best-effort），让流程可重复执行。"""
    lf = _client()
    try:
        lf.delete_dataset_run(dataset_name=dataset_name, run_name=run_name)
    except Exception:
        pass


def compare_hint(host: str, dataset_name: str, baseline_run: str, candidate_run: str) -> str:
    """对比在 Langfuse UI：Datasets → 选两个 run → Compare（baseline vs candidate，绿/红增减）。"""
    return (
        f"{host} → Datasets → {dataset_name} → Runs：选 {baseline_run} 与 "
        f"{candidate_run} → Compare（Charts 聚合 / Outputs 逐条对比）。"
    )
