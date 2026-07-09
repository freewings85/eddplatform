"""EDD 配置：话痨说车 chatagent 两套方案（真实 dogfood 对比）。

这是"一个系统含多个项目 + 对应 git/分支 + 启动命令/参数/端口/env + 依赖的基础服务"的
声明式配置——EDD 据此 build 镜像并部署到 k8s 一个 namespace 里跑评估。

方案A(2.0) = orchestrator@2.0 + workflows@2.0 + chatagent2/mainagent@2.0 + toolprovider
方案B(2.3) = orchestrator@2.3 + chatagent3{mainagent,sessionstore,toolexecutor}@2.3
基础服务：kafka + postgres（方案A 另需 redis/mysql/temporal；本机 USE_NACOS=false 不起 Nacos）。

服务发现：容器内用 k8s Service DNS（同 namespace 直接用服务名，如 kafka:9092、
sessionstore:8120），把各项目 .env.local 里的 127.0.0.1 换成服务名。真实 LLM 用项目自带
DashScope key（deepseek-v4-flash）。
"""

from eddplatform.domain.models import BaseService, Module, System, SystemVersion

GH = "/mnt/e/Documents/github"
CA3 = f"{GH}/com.celiang.hlsc.service.ai.chatagent3"
ORCH = f"{GH}/com.celiang.hlsc.service.ai.orchestrator"
CA2 = f"{GH}/com.celiang.hlsc.service.ai.chatagent2"
WF = f"{GH}/com.celiang.hlsc.service.ai.workflows"
TP = f"{GH}/com.celiang.hlsc.service.ai.toolprovider"

# 项目自带、已提交在 .env.local 里的 DashScope key（deepseek-v4-flash）。
LLM_KEY = "sk-8cf834ae11f94a9d91f7a98960e116cb"
LITELLM_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# OTel 指标推送到集群内 collector（读 2.0 分布式各进程的逐 generation token：BMA
# classify/turn_router + collect + workflows 都发 gen_ai.client.token.usage，含 cache_read，
# 前门 SSE 看不到它们）。chatagent core.observability.metrics 的开关是 OTEL_METRICS_ENABLED。
OTLP_METRICS = {
    "OTEL_METRICS_ENABLED": "true",
    "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": "http://otelcol:4318/v1/metrics",
    "OTEL_METRIC_EXPORT_INTERVAL_MS": "2000",
}

# ── 基础服务 ────────────────────────────────────────────────────────────────
KAFKA = BaseService(
    name="kafka", image="apache/kafka:3.9.0", ports=[9092],
    env={
        "KAFKA_NODE_ID": "1",
        "KAFKA_PROCESS_ROLES": "broker,controller",
        "KAFKA_CONTROLLER_QUORUM_VOTERS": "1@localhost:9093",
        "KAFKA_LISTENERS": "PLAINTEXT://:9092,CONTROLLER://:9093",
        # k8s：advertised 必须是 Service DNS，客户端连 kafka:9092 才拿得到可路由地址
        "KAFKA_ADVERTISED_LISTENERS": "PLAINTEXT://kafka:9092",
        "KAFKA_CONTROLLER_LISTENER_NAMES": "CONTROLLER",
        "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP": "CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT",
        "KAFKA_INTER_BROKER_LISTENER_NAME": "PLAINTEXT",
        "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR": "1",
        "KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR": "1",
        "KAFKA_TRANSACTION_STATE_LOG_MIN_ISR": "1",
        "KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS": "0",
        "KAFKA_AUTO_CREATE_TOPICS_ENABLE": "true",
    },
)
POSTGRES = BaseService(
    name="postgres", image="postgres:16", ports=[5432],
    env={"POSTGRES_PASSWORD": "postgres", "POSTGRES_DB": "sessionstore"},
)
# Temporal 轻量 dev-server（内存持久化，自动建 default namespace，无需单独 DB）。
TEMPORAL = BaseService(
    name="temporal", image="temporalio/admin-tools:1.30.1", ports=[7233],
    command=["temporal", "server", "start-dev", "--ip", "0.0.0.0", "--namespace", "default"],
)
# 本地 mock datamanager（给 searchshops/searchcoupons 固定假数据）。
DATAMANAGER = BaseService(name="datamanager", image="edd/mock-datamanager:1", ports=[50401])

# ── 方案B(2.3) 进程 ─────────────────────────────────────────────────────────
_B_COMMON_MAINAGENT_ENV = {
    "SERVER_HOST": "0.0.0.0", "SERVER_PORT": "8100",
    "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
    "CHAT_STREAM_TOPIC": "chat-events", "CHAT_ASYNC_TOPIC": "chat-events",
    "LLM_STUB": "0", "LITELLM_BASE_URL": LITELLM_BASE, "LITELLM_KEY_LLM_FLASH": LLM_KEY,
    "SESSION_STORE_BASE_URL": "http://sessionstore:8120",
    # DBOS 系统库用 Postgres（SQLite 路径在本镜像有 application_versions.version_timestamp
    # NOT NULL 迁移 bug；.env.local 也注明多实例/生产必须 Postgres）。与 sessionstore 共用
    # 同一 PG 实例的 sessionstore 库，DBOS 建自己的 dbos_* 表，不冲突。
    "DBOS_SYSTEM_DATABASE_URL": "postgresql://postgres:postgres@postgres:5432/sessionstore",
    "TEMPORAL_ADDRESS": "temporal:7233", "TEMPORAL_NAMESPACE": "default",
    "TOOLEXECUTOR_CONTROL_BASE_URL": "http://toolexecutor:8310",
    "OTEL_METRICS_ENABLED": "true",
}
B_MAINAGENT = Module(name="mainagent", git_url=CA3,
                     dockerfile="services/mainagent/Dockerfile", context=".",
                     ports=[8100], env=dict(_B_COMMON_MAINAGENT_ENV))
B_SESSIONSTORE = Module(name="sessionstore", git_url=CA3,
                        dockerfile="services/sessionstore/Dockerfile", context=".",
                        ports=[8120],
                        env={"SERVER_HOST": "0.0.0.0", "SERVER_PORT": "8120",
                             "PG_DSN": "postgresql://postgres:postgres@postgres:5432/sessionstore"})

# toolexecutor：search_shops/search_coupons 经它跑 Temporal workflow + 调 datamanager。
# TE_REGISTRY_DATABASE_URL 留空 → 中断控制子系统禁用，但非中断的 search 类工具仍可用（省一张 PG 库）。
B_TOOLEXECUTOR = Module(
    name="toolexecutor", git_url=CA3,
    dockerfile="services/toolexecutor/Dockerfile", context=".", ports=[8300, 8310],
    env={
        "SERVER_HOST": "0.0.0.0", "SERVER_PORT": "8300", "USE_NACOS": "FALSE",
        "DATAMANAGER_BASE_URL": "http://datamanager:50401/service_ai_datamanager",
        "DATAMANAGER_HTTP_TIMEOUT": "10",
        "TEMPORAL_ADDRESS": "temporal:7233", "TEMPORAL_NAMESPACE": "default",
        # 控制 API(:8310，mainagent 靠它 start_or_attach 起工具 workflow)仅当配了登记库才启动，
        # 故必须配。与 sessionstore/DBOS 共用同一 PG 库(建自己的 te_* 表，不冲突)，免再建库。
        "TE_REGISTRY_DATABASE_URL": "postgresql://postgres:postgres@postgres:5432/sessionstore",
        "TE_KAFKA_BOOTSTRAP_SERVERS": "kafka:9092", "TE_CHAT_EVENTS_TOPIC": "chat-events",
        "TE_CONTROL_HOST": "0.0.0.0", "TE_CONTROL_PORT": "8310",
        # 小模型(classify/query 构造)走 DashScope（Azure 未配 → 用 OpenAI 兼容 SMALL_MODEL_*）
        "SMALL_MODEL_ENDPOINT": LITELLM_BASE, "SMALL_MODEL_API_KEY": LLM_KEY,
        "SMALL_MODEL_NAME": "qwen3-30b-a3b",
        "CLASSIFY_RAG_THRESHOLD": "0.5", "CLASSIFY_MAX_RESULTS": "3",
        "SEARCH_SHOP_DEFAULT_RADIUS_M": "20000", "SEARCH_RADIUS_ADJUST_STEP_M": "5000",
    },
)

# guide 场景最小闭环：mainagent + sessionstore + kafka + postgres（不需 toolexecutor/temporal）
SOLUTION_B_GUIDE_MODULES = [B_SESSIONSTORE, B_MAINAGENT]
SOLUTION_B_GUIDE_BASE = [KAFKA, POSTGRES]

# 完整方案B(三场景)：+ toolexecutor + temporal + mock datamanager
SOLUTION_B_MODULES = [B_SESSIONSTORE, B_MAINAGENT, B_TOOLEXECUTOR]
SOLUTION_B_BASE = [KAFKA, POSTGRES, TEMPORAL, DATAMANAGER]

VERSION_B = SystemVersion(
    id="chatagent-2.3", system_id="chatagent", label="2.3",
    module_pins={"sessionstore": "2.3", "mainagent": "2.3", "toolexecutor": "2.3"},
    note="方案B(2.3 clean)：orchestrator直连+chatagent3(DBOS)+toolexecutor(Temporal)。",
)
VERSION_B_GUIDE = SystemVersion(   # guide 子集：只钉 2 个进程（render 按 module_pins 决定服务）
    id="chatagent-2.3-guide", system_id="chatagent", label="2.3",
    module_pins={"sessionstore": "2.3", "mainagent": "2.3"},
)

# ══════════════════════════════════════════════════════════════════════════
# 方案A(2.0)：orchestrator@2.0 + workflows + chatagent2/mainagent@2.0 + toolprovider
# 评估直接打 chatagent2 mainagent /chat/run（自带 ChatWorkflow Temporal worker）；按场景传
# agent_type 跑对应 agent。基础服务：kafka + redis(会话锁) + temporal + mock datamanager
# （USE_NACOS=FALSE 不起 Nacos；MySQL 非启动硬依赖，先不部署）。
# ══════════════════════════════════════════════════════════════════════════
REDIS = BaseService(name="redis", image="redis:7", ports=[6379])
# chatagent2 用 MySQL 做 interrupt_store + 会话历史（root/root，db=sessionstore）。
MYSQL = BaseService(name="mysql", image="mysql:5.7", ports=[3306],
                    env={"MYSQL_ROOT_PASSWORD": "root", "MYSQL_DATABASE": "sessionstore"})

A_MAINAGENT = Module(
    name="ca2-mainagent", git_url=CA2,
    dockerfile="src/mainagent/Dockerfile", context=".", ports=[8100],
    env={
        "SERVER_PORT": "8100", "USE_NACOS": "FALSE",
        "TEMPORAL_HOST": "temporal:7233", "TEMPORAL_NAMESPACE": "default",
        "TEMPORAL_TASK_QUEUE": "chat-task-queue", "TOOLPROVIDER_TASK_QUEUE": "toolprovider",
        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092",
        "CHAT_STREAM_TOPIC": "chat-stream-events", "CHAT_ASYNC_TOPIC": "chat-async-events",
        "DATAMANAGER_BASE_URL": "http://datamanager:50401/service_ai_datamanager",
        "SESSION_LOCK_BACKEND": "redis", "REDIS_URL": "redis://redis:6379/0",
        "MYSQL_HOST": "mysql", "MYSQL_PORT": "3306", "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "root", "MYSQL_DB": "sessionstore",
        "LITELLM_BASE_URL": LITELLM_BASE, "LITELLM_KEY_LLM": LLM_KEY,
        "LITELLM_KEY_LLM_FLASH": LLM_KEY,
        "OTEL_SERVICE_NAME": "chatagent2-mainagent", **OTLP_METRICS,
    },
)
# toolprovider 直接 build 成 edd/chatagent-toolprovider（无 tag，render 补 :2.0）。
A_TOOLPROVIDER = Module(
    name="toolprovider", git_url=TP, image="edd/chatagent-toolprovider",
    dockerfile="Dockerfile", context=".", ports=[8300],
    env={
        "SERVER_PORT": "8300", "USE_NACOS": "FALSE",
        "TEMPORAL_HOST": "temporal:7233", "TEMPORAL_ADDRESS": "temporal:7233",
        "TEMPORAL_NAMESPACE": "default", "TOOLPROVIDER_TASK_QUEUE": "toolprovider",
        "DATAMANAGER_BASE_URL": "http://datamanager:50401/service_ai_datamanager",
        "DATAMANAGER_HTTP_TIMEOUT": "10",
        "SMALL_MODEL_ENDPOINT": LITELLM_BASE, "SMALL_MODEL_API_KEY": LLM_KEY,
        "SMALL_MODEL_NAME": "qwen3-30b-a3b",
    },
)

# guide 子集（不需 toolprovider/datamanager）
SOLUTION_A_GUIDE_MODULES = [A_MAINAGENT]
SOLUTION_A_GUIDE_BASE = [KAFKA, REDIS, MYSQL, TEMPORAL]
VERSION_A_GUIDE = SystemVersion(
    id="chatagent-2.0-guide", system_id="chatagent", label="2.0",
    module_pins={"ca2-mainagent": "2.0"})

# 完整方案A(三场景)：+ toolprovider + datamanager
SOLUTION_A_MODULES = [A_MAINAGENT, A_TOOLPROVIDER]
SOLUTION_A_BASE = [KAFKA, REDIS, MYSQL, TEMPORAL, DATAMANAGER]
VERSION_A = SystemVersion(
    id="chatagent-2.0", system_id="chatagent", label="2.0",
    module_pins={"ca2-mainagent": "2.0", "toolprovider": "2.0"},
    note="方案A(2.0)：chatagent2(Temporal ChatWorkflow)+toolprovider。",
)

# ══════════════════════════════════════════════════════════════════════════
# 前门（orchestrator）—— 完整系统"前门到前门"对比所需的编排入口层。
# 直接打下游 mainagent 只测到"某个点"（2.0 collect agent 只到参数抽取，绕过
# workflows+BMA 编排）；经前门 /chat/stream 才把两套系统的**完整链路**都测进去。
#   方案A(2.0): orchestrator@2.0 → workflows(BMA classify→capability) → chatagent2 + toolprovider
#   方案B(2.3): orchestrator@2.3 → chatagent3 → toolexecutor（直连，无 workflows/BMA）
# ══════════════════════════════════════════════════════════════════════════

# ── 方案A(2.0) 前门三件套：orchestrator + workflows(Temporal worker) + BMA ──
A_ORCH = Module(
    name="orchestrator", git_url=ORCH, dockerfile="Dockerfile", context=".", ports=[7100],
    env={
        "SERVER_HOST": "0.0.0.0", "SERVER_PORT": "7100",
        "ACTIVE": "local", "USE_NACOS": "FALSE",
        "AGENT_SERVICE_URL": "http://ca2-mainagent:8100",
        "TEMPORAL_ADDRESS": "temporal:7233", "TEMPORAL_NAMESPACE": "default",
        "CHAT_TURN_ROOT_WORKFLOW_TYPE": "ChatTurnRootWorkflow",
        "CHAT_TURN_TASK_QUEUE": "chat-turn-workers",
        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092", "CHAT_EVENTS_TOPIC": "chat-events",
    },
)
# workflows：单进程 = Temporal worker(ChatTurnRoot+DirectRouter/Coordinator+capabilities)
# + FastAPI 健康口(8200)，跑在 chat-turn-workers 队列。orchestrator 起 workflow → 它执行。
A_WORKFLOWS = Module(
    name="workflows", git_url=WF, dockerfile="Dockerfile", context=".", ports=[8200],
    env={
        "ACTIVE": "local", "USE_NACOS": "FALSE",
        "TEMPORAL_ADDRESS": "temporal:7233", "TEMPORAL_NAMESPACE": "default",
        "CHAT_TURN_TASK_QUEUE": "chat-turn-workers", "TEMPORAL_DEBUG": "true",
        "WORKFLOWS_HEALTH_PORT": "8200", "WORKFLOWS_INTERNAL_HTTP_ENABLED": "true",
        # 下游 chatagent2 mainagent（guide/collect agent 经 HTTP /chat/stream）
        "AGENT_SERVICE_URL": "http://ca2-mainagent:8100", "AGENT_STREAM_PATH": "/chat/stream",
        "AGENT_HTTP_TIMEOUT": "90",
        # BMA（每轮 classify 路由 + searchshops/coupons turn_router）
        "BMA_BASE_URL": "http://bma:8103",
        "BMA_CLASSIFY_URL": "http://bma:8103/classify",
        "BMA_TURN_ROUTER_SEARCHSHOPS_URL": "http://bma:8103/turn_router/searchshops",
        "BMA_TURN_ROUTER_SEARCHCOUPONS_URL": "http://bma:8103/turn_router/searchcoupons",
        # 搜索走 mock datamanager（SHOP_SEARCH_URL/COUPON 留空→从 DATAMANAGER_BASE_URL 派生路径）
        "DATAMANAGER_BASE_URL": "http://datamanager:50401/service_ai_datamanager",
        "DATAMANAGER_HTTP_TIMEOUT": "10",
        # 地理编码服务（按地名解析坐标）——本环境无真实后端；用例带坐标时不触发，
        # 触发则该次搜索降级。置占位避免 import 期报错（调用时才 RuntimeError）。
        "ADDRESS_SERVICE_URL": "http://datamanager:50401",
        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092", "CHAT_EVENTS_TOPIC": "chat-events",
        # workflows 直写 session_search_history 到 MySQL(库名 orchestrator，需预建)；
        # 写失败 fail-soft（下游退化成"无 search_result 上下文"，对话仍跑）。
        "MYSQL_HOST": "mysql", "MYSQL_PORT": "3306", "MYSQL_USER": "root",
        "MYSQL_PASSWORD": "root", "MYSQL_DB": "orchestrator",
        "SMALL_MODEL_ENDPOINT": LITELLM_BASE, "SMALL_MODEL_API_KEY": LLM_KEY,
        "SMALL_MODEL_NAME": "qwen3-30b-a3b",
        "LOGFIRE_ENABLED": "false",   # traces 关掉免噪声；metrics 单独走 OTLP
        "OTEL_SERVICE_NAME": "hlsc-workflows", **OTLP_METRICS,
    },
)
# BMA(business_map_agent)：纯 LLM 服务，/classify + /turn_router/*。llm.yaml 用
# LITELLM_BASE_URL + LITELLM_KEY_BMA_{SLM,LLM}(模型 qwen3.5-flash / deepseek-v4-flash)。
A_BMA = Module(
    name="bma", git_url=CA2,
    dockerfile="src/subagents/business_map_agent/Dockerfile", context=".", ports=[8103],
    env={
        "ACTIVE": "local", "USE_NACOS": "FALSE",
        "SERVER_HOST": "0.0.0.0", "SERVER_PORT": "8103", "LOG_DIR": "logs",
        "LITELLM_BASE_URL": LITELLM_BASE,
        "LITELLM_KEY_BMA_SLM": LLM_KEY, "LITELLM_KEY_BMA_LLM": LLM_KEY,
        "OTEL_SERVICE_NAME": "business-map-agent", **OTLP_METRICS,
    },
)
SOLUTION_A_FRONTDOOR_DELTA = [A_ORCH, A_WORKFLOWS, A_BMA]
VERSION_A_FRONTDOOR = SystemVersion(
    id="chatagent-2.0-frontdoor", system_id="chatagent", label="2.0",
    module_pins={"orchestrator": "2.0", "workflows": "2.0", "bma": "2.0"},
)

# ── 方案B(2.3) 前门：orchestrator@2.3（直连 chatagent3，无 workflows/BMA）──
B_ORCH = Module(
    name="orchestrator", git_url=ORCH, dockerfile="Dockerfile", context=".", ports=[7100],
    env={
        "SERVER_HOST": "0.0.0.0", "SERVER_PORT": "7100",
        "ACTIVE": "local", "USE_NACOS": "FALSE",
        "CHATAGENT3_SERVICE_URL": "http://mainagent:8100",
        "KAFKA_BOOTSTRAP_SERVERS": "kafka:9092", "CHAT_EVENTS_TOPIC": "chat-events",
    },
)
SOLUTION_B_FRONTDOOR_DELTA = [B_ORCH]
VERSION_B_FRONTDOOR = SystemVersion(
    id="chatagent-2.3-frontdoor", system_id="chatagent", label="2.3",
    module_pins={"orchestrator": "2.3"},
)

# 前门入口：两套都经 orchestrator :7100 /chat/stream（同一入口契约，前门到前门可比）
FRONTDOOR = {"2.3": ("orchestrator", 7100), "2.0": ("orchestrator", 7100)}

# 每套方案的入口进程 + 场景→agent_type 映射（2.3 单 agent 不需 agent_type；2.0 需要）
ENTRY = {"2.3": "mainagent", "2.0": "ca2-mainagent"}
AGENT_TYPE_2_0 = {"guide": "guide",
                  "searchshops": "searchshops_collect_v2",
                  "searchcoupons": "searchcoupons_collect_v2"}

CHATAGENT_SYSTEM = System(
    id="chatagent", name="话痨说车 chatagent",
    modules=SOLUTION_B_MODULES, base_services=SOLUTION_B_BASE,
)
