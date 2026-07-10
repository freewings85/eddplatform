# 本地 Temporal（发布评估流水线执行引擎）

EddPlatform 的发布评估编排逻辑已在 `orchestration/pipeline.py`（纯 Python）跑通；
Temporal 只换执行引擎，让「建 env→跑→评→对比→销」可重试 / 可观测 / 可断点续跑。
逻辑等价性由 `tests/test_temporal_workflow.py` 用 temporalio 自带 in-memory 测试环境
保证（**不需要本 server**）。本 server 用于 live 端到端演示。

## 起 server

```bash
cd deploy/temporal
docker compose up -d          # 拉 postgres + temporalio/auto-setup + ui
```

- gRPC：`localhost:7233`（应用连这个）
- Web UI：http://localhost:8233 （看 workflow run / activity 重试）

## 跑端到端 demo

```bash
pip install -e '.[temporal]'
python examples/temporal_release_demo.py       # 连 :7233，MockProvider 跑一轮
```

UI 里应能看到一个 `edd-release-*` workflow，Completed，含 create_env/evaluate_version/
destroy_env 三类 activity。集群在时把 demo 里的 `MockProvider()` 换成 `K8sProvider()`
即真拉 k8s 一次性环境。

## 关
```bash
docker compose down           # 加 -v 连数据卷一起删
```
