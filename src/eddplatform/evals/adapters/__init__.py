"""可选适配器：把中立评估对接到具体生态。

- ``pydantic_evals``  给 pydantic-ai 团队的可选执行后端（需 extra: pip install -e '.[pydantic-evals]'）
- （规划）``langfuse``  评估器管理 / 存储 / dataset-run 对比

核心引擎（evals/engine.py）不依赖这些；不装也能完整跑评估。
"""
