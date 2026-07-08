"""Temporal 编排薄壳：把 pipeline 的每步登记成 activity / workflow。

发布评估流水线的**逻辑**已在 ``pipeline.run_release_evaluation``（纯 Python）里跑通。
Temporal 只换执行引擎：把「渲染 manifest → 建 env → 部署 → 跑 → 评 → 对比 → 销」
登记为可重试 / 可观测 / 可断点续跑的 activity。

本机未装 ``temporalio``（也无需长跑 server 即可离线跑逻辑）：``available()`` 反映是否
可用；``build_worker`` 在缺依赖时报错。真实部署时 server 可用 docker 起。
"""

from __future__ import annotations


def available() -> bool:
    try:
        import temporalio  # noqa: F401

        return True
    except ImportError:
        return False


def build_worker(*args, **kwargs):
    """构造 Temporal worker（注册发布评估 workflow + activities）。需 temporalio。"""
    if not available():
        raise RuntimeError(
            "Temporal 编排需要 temporalio：pip install -e '.[temporal]'，"
            "并起一个 Temporal server（可 docker）。逻辑本身可先用 "
            "orchestration.pipeline.run_release_evaluation 离线跑通。"
        )
    raise NotImplementedError(
        "真实部署时在此注册 workflow/activities，把 pipeline 各步包成 activity。"
    )
