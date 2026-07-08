"""发布评估编排（框架无关核心 + 可插拔 provider）。

核心 ``run_release_evaluation`` 是纯 Python：为两个系统版本各拉一次性环境 → 跑用例
→ 评分 → 对比 → 销毁。真实底座（Garden/k8s、Harbor、Temporal）通过 provider / 薄壳
接入，本地用 MockProvider 即可离线跑通整条流水线。
"""
