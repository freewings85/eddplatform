"""评估引擎（推荐、主干）：Langfuse —— 复用优秀开源，不自研。

Langfuse 负责：dataset run / experiment、评估器（LLM-judge 模板）、score、
**baseline vs candidate 并排对比**、OTel 追踪。EddPlatform 只做薄胶水：
把沙箱里拉起的系统入口（Target）按用例跑一遍（task loop）→ 建 dataset run、
写 score → 到 Langfuse 看老新对比。

需要一个 Langfuse 实例（自托管或云）+ 环境变量：
    LANGFUSE_HOST, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
安装：``pip install -e '.[langfuse]'``

⚠️ Langfuse SDK 各版本 API 略有差异（get_dataset / item.run / create_score）。
下方按常见形态实现，真实接入时对着你装的版本核一遍。
"""

from __future__ import annotations

from typing import Any, Callable

from eddplatform.domain.models import Dataset as DomainDataset
from eddplatform.evals.engine import EvalContext, Evaluator

_DATA_TYPE = {"assertion": "BOOLEAN", "score": "NUMERIC", "label": "CATEGORICAL"}


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
    """把用例集推到 Langfuse dataset（可维护、可作为发布评估的输入）。"""
    lf = _client()
    lf.create_dataset(name=dataset.name)
    for c in dataset.cases:
        lf.create_dataset_item(
            dataset_name=dataset.name,
            input=c.inputs,
            expected_output=c.expected_output,
            metadata={
                **c.metadata,
                "case_version": c.case_version,
                "applicable_versions": c.applicable_versions,
            },
        )
    lf.flush()


def run_experiment(
    dataset_name: str,
    task: Callable[[Any], Any],
    run_name: str,
    evaluators: dict[str, Evaluator],
) -> str:
    """跑一次 dataset run：对每个 item 调 task → 建 trace → 打分写回 Langfuse。

    ``run_name`` 建议用系统版本标识（如 ``insurance-v2``），这样两个 run 就能在
    Langfuse Compare 视图里作 baseline vs candidate 对比。

    这里用中立评估器算分再 push（薄胶水）；也可改为在 Langfuse 侧配置 managed
    LLM-judge 评估器，让 Langfuse 自己异步打分——两条路都行。
    """
    lf = _client()
    dataset = lf.get_dataset(dataset_name)
    for item in dataset.items:
        with item.run(run_name=run_name) as root:      # 建立 dataset-run trace
            output = task(item.input)
            root.update(output=output)
            ctx = EvalContext(
                inputs=item.input, output=output, expected_output=item.expected_output
            )
            for ev in evaluators.values():
                oc = ev.evaluate(ctx)
                root.score_trace(
                    name=oc.name,
                    value=oc.value,
                    data_type=_DATA_TYPE[oc.output_type.value],
                    comment=oc.reason,
                )
    lf.flush()
    return run_name


def compare_hint(dataset_name: str, baseline_run: str, candidate_run: str) -> str:
    """对比在 Langfuse UI：选两个 run → Compare（baseline vs candidate，绿/红增减）。"""
    return (
        f"Langfuse → Datasets → {dataset_name} → Runs：选 {baseline_run} 与 "
        f"{candidate_run} → Compare（Charts 聚合 / Outputs 逐条对比）。"
    )
