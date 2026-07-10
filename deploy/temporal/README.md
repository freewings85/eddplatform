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

## 本机验证记录（2026-07-10）与排坑

已用 `temporalio/auto-setup` + postgres 真起 server，`examples/temporal_release_demo.py` 对真 server 端到端跑通（改善 1 / 回归 0 / 共有 3，需求 R-101 未达→达标），server 侧记录到 `ReleaseEvaluationWorkflow`（task queue `edd-release-eval`）。踩坑：

- **host :7233 可能被占**：WSL2 mirrored networking 下，Windows 侧监听的 7233 会映进 WSL，`up` 报 `address already in use`。改用另一 host 端口（把 compose 的 `7233:7233` 换成如 `7234:7233`，demo 连 `localhost:7234`），或在 Windows 侧释放 7233。
- **`temporalio/ui` 镜像可能拉不动**：受限公网下该镜像经 mirror 不可达；UI 仅作可视化，可只起 server + 库：`docker compose up -d postgresql temporal`，demo 照常跑，不影响功能。
- **并行 pull 易超时**：`docker compose pull` 并行拉多镜像时 `auto-setup` 易超时；单独 `docker pull temporalio/auto-setup:1.25.2` 更稳。
