# 本地自托管 Langfuse（评估引擎）

基于官方 compose，改了三处冲突端口：**web 3100**、postgres 5433、redis 6380（内网仍用默认）。
用 `LANGFUSE_INIT_*` 无头初始化一个项目 + 固定 API key，便于脚本直接连。

## 起停

```bash
cp .env.example .env         # 首次：把 CHANGEME 换成随机值
#   NEXTAUTH_SECRET / SALT: openssl rand -hex 24    ENCRYPTION_KEY: openssl rand -hex 32
docker compose up -d         # 首次会拉镜像（postgres/clickhouse/redis/minio/langfuse×2）
docker compose ps            # 等 langfuse-web 变 healthy
#   UI: http://localhost:3100  （admin@eddplatform.local / eddplatform-admin-123）
docker compose down          # 停；加 -v 连数据卷一起删
```

## 连接（供 SDK / 脚本用）

```bash
export LANGFUSE_HOST=http://localhost:3100
export LANGFUSE_PUBLIC_KEY=pk-lf-eddplatform-local
export LANGFUSE_SECRET_KEY=sk-lf-eddplatform-local
python examples/langfuse_run.py     # 端到端：sync 用例 → 跑 v1/v2 → Compare 对比
```

> 端口若仍冲突，改 `docker-compose.yml` 里 `3100:3000` / `.env` 的 `NEXTAUTH_URL`。
