# chatagent 真实对比 dogfood —— 暴露并改进 EDD 的不足

日期：2026-07-09
背景：用 EDD 这套机制对真实的 chatagent 重构(方案A 2.0 ↔ 方案B 2.3)做一次端到端的老新
评估对比（guide/searchshops/searchcoupons，真实 LLM + 本地 mock datamanager，两套 4 进程 +
各自基础服务，全部由 EDD 配置→build→部署到本地 k3d 真集群→跑用例→评分）。目标之一是**借这
次实战发现并改进 EDD 本身**。本文档汇总这轮暴露的问题与已落地/待办的改进。

## 一、EDD 已落地的改进（本轮 TDD 补齐）

| # | 问题（dogfood 暴露） | 改进 |
|---|---|---|
| 1 | `Module` 只有 git/branch/image，描述不了"进程怎么启动" | 加 `command`/`args`/`ports`/`env`/`context`；`image` 改可选(无则从 git build) |
| 2 | `System` 声明不了依赖的基础服务 | 加 `BaseService`(name/image/ports/env/**command**/args) + `System.base_services`；temporal 需 `command=temporal server start-dev` 故 BaseService 也要 command |
| 3 | 无"跑完是否清理环境"开关 | pipeline `run_release_evaluation(cleanup=)` + `RunRecord.cleanup_after`(默认 True，False 留现场排查) |
| 4 | 没有真实环境 provider | `integrations/k8s.py::K8sProvider`(kubectl 部署 manifest 到 namespace→等就绪→销)；真集群验证通过 |
| 5 | 没有"按分支 build 镜像"能力 | `orchestration/build.py::build_module_image`(git worktree checkout ref→docker build→k3d import) |
| 6 | k8s namespace 名不能含点，版本号 `2.3` 直接当 ns 名会失败 | `_namespace_name` 清洗(`2.3`→`edd-2-3`) |
| 7 | 集群内 containerd 不认宿主 registry mirror，pause 镜像都拉不动 | 建集群带 `--registry-config`(docker.io/ghcr.io→mirror)；见 k3d-howto 记忆 |
| 8 | 导入的本地镜像被 k8s 重新去公网拉 | Deployment 固定 `imagePullPolicy: IfNotPresent` + `k3d image import` |
| 9 | **pod DNS `ndots:5` + 宿主通配 search 域致外部 LLM 域名(dashscope)误解析** | pod 设 `dnsConfig ndots:1`(外部域名先按绝对名解析，服务名仍走 search) |
| 10 | build 产出镜像名与 render_manifest 部署引用名不一致 | render 无 image 时复用 `build.image_ref`(`edd/<sys>-<name>:<tag>`) |
| 11 | **git-worktree 干净 checkout 漏掉生成的/被 .gitignore 的运行期必需文件**(如 chatagent2 的 `allprojects.md`) | `build_module_image(from_working_tree=True)`：直接从工作树 build |
| 12 | 写死打某个下游进程 /chat/run，只测"某个点"、跨架构不公平（见 §二教训） | **前门入口适配器** `examples/chatagent/frontdoor.py`：经前门 orchestrator `/chat/stream` 驱动完整一轮，聚合 SSE(`text`/`tool_call_*`/`usage`/`chat_request_end`)成与 /chat/run 同形的 `{output,tool_calls,usage,latency_s,error}`，评估器零改动复用。纯解析核心 `iter_sse_events`/`aggregate_events` 有 TDD 单测(tests/test_frontdoor.py) |
| 13 | 多进程系统的完整前门链路要靠 EDD 一键拉起（含 BMA 独立进程、workflows Temporal worker、跨库 MySQL） | 前门三件套(orchestrator@2.0 + workflows worker + BMA :8103)+ orchestrator@2.3 均由 EDD build→部署 delta 到既有 namespace(幂等 apply，不动在跑 pod)；MySQL 预建 `orchestrator` 库+载 workflows schema |

## 二、对比方法学上的发现

- **跨架构对比要在结果/参数层，而非内部工具序列**：方案A(BMA 路由 + capability agents)与方案B
  (单 hlsc_agent + 工具) 内部工具不同(2.0: SpawnAgent/search_shops；2.3: confirm_business/
  resolve_project_terms/search_shops)，"工具序列"断言不通用。可比的是：**search_* 工具的参数
  抽取准确率(criteria_subset)**、**时延**、**token 成本**、以及 guide 的**最终文案质量(LLM 裁判)**。

- **⚠️ 入口层级不对齐 → 得出过错误结论（本轮最大教训）**：第一版对比里 2.3 打 chatagent3
  mainagent /chat/run(单 agent 即端到端)，而 2.0 只打 chatagent2 mainagent /chat/run + `agent_type`
  ——**这绕过了 2.0 的 workflows+BMA 编排层（正是 2.3 重构删掉的那层）**，且 `*_collect_v2` 只是
  收集 agent(产搜索参数、不产最终文案)。于是 2.0 被测的是"某个点"、天然又快又省，据此得出
  **"2.3 比旧方案慢 2-3x、token 贵 3-7x"是错的**。用户一句"不可能，怎么会新方案还慢"点破。
- **修正：前门到前门对比完整系统**。两套都经各自**前门 orchestrator :7100 `/chat/stream`** 驱动
  完整一轮（2.0: orchestrator→workflows→BMA classify/turn_router→chatagent2 collect+toolprovider；
  2.3: orchestrator→chatagent3→toolexecutor），SSE 到 `chat_request_end` 即一轮结束。此时 2.0 也
  含 BMA 分类 LLM + workflows 编排开销，才可比。**结论翻转**：端到端时延两者**同一量级**（各 5 用例均值
  A→B：guide 3.6→4.4s、shops 9.7→10.6s、coupons 7.9→10.0s），2.3 只**略慢 ~10–25%（+0.8~2s）**，
  **绝不是第一版所称的"慢 2–3x"**——那个倍数纯是拿"2.0 的收集 agent 捷径"对"2.3 的完整链路"比出来的假象。
- **文案质量(架构中立 judge/deny)：2.3 ≥ 2.0**，guide 尤明显(2.0 67% → 2.3 100%；2.0 guide 偏简短、
  少了 Skill/rubric 期望)，search 两者均 100%。
- **失败用例数别当质量信号**：前门 SSE 对 2.0 不落 search 工具 args、也不走 Skill 工具，故 2.0 的
  `criteria_subset`/`tools` 断言"找不到工具"而失败——是前门适配器对 2.0 的**测量不对等**，非真实缺陷。
  可比的是中立的 judge/deny 列。
- **可比性要逐轴诚实标注**：① **时延**=前门完整一轮墙钟，端到端公平可比（头号指标）；② **文案质量**
  =judge/deny 断言，架构中立公平；③ **token**：2.3 单 agent 一次 usage 事件即全量，2.0 的 usage 事件
  只带叶子 agent(chatagent2)用量、**漏掉 BMA + workflows 小模型（分处独立进程、不发 usage 到
  chat-events）→ 2.0 token 系统性低估**，跨架构 token 对比须靠 Langfuse trace 汇总；④ **参数抽取**：
  2.3 前门 SSE 带 `search_*(query=...)` 完整 args，2.0 前门 search 工具 args 不落 SSE → 前门侧不对等，
  只能用"直接打下游 agent"的探针口径(compare.py)另测。**别把不对等的轴当结论**。

## 二·补：token "消耗去哪 + 多轮缓存"根因（systematic-debugging 实证）

**2.3 单轮 token 高的根因**：2.3 collapse 成单个 `hlsc_agent`，把全部工具本体塞进一份常驻 prompt——
`search_shops.md`(6962 字)+`search_coupons.md`(6198 字)+hlsc 系统提示+`allprojects.md` 本体 ≈ **~13k
token**（实测 guide 裸调用 input=12907，几乎全是它）。单 agent **无廉价前置路由**：问"你是谁"也照吞 13k。
再叠 **多步 ReAct**（confirm_business→resolve_project_terms→search_shops→收尾 ≈ 5 次 LLM 调用），每步重发
这 13k + 累积历史 → 单 shops 轮 raw input 52,563。2.0 把同样的活拆成**小而专**的提示（BMA classify 2818 字 /
turn_router 2833 字 / collect main.md 2594 字），且搜索执行 + 最终文案**不花 LLM**（workflows/query_builder/
模板）。两者 LLM 调用数都 ≈5，差的是**每次调用的 prompt 体积**（13k vs ~2k）——这也解释 2.3 略慢。

**但多轮缓存翻转单轮结论（6 轮 商家↔活动 来回切实测）**：
- **2.3 整体缓存命中 87%**；暖起来后每轮只**计费 ~700–3,400 fresh token**（命中 94–95%）。**切换业务不破坏
  缓存**——那 ~13k 工具本体是**业务无关的恒定前缀**，查活动/查商家都是同一份，一直命中。
- **2.0 整体命中仅 49%**，切回业务那轮掉到 55%：每次切业务要重跑 BMA classify(全新)+换 turn_router(全新)+
  换 collect agent(与另一业务无共享前缀)。**2.3 那个"单体缺点"在切业务多轮场景反成缓存优点**。
- **口径修正**：`计费input=input-cache_read` 只是**下界**（缓存 token 非免费，按各家折扣 ~10–40% input 价计），
  raw 是上界；且 2.3 的 usage 是**单 agent 全量**、2.0 的是**漏了 BMA 的低估值**。故"暖态谁更省"须逐 generation
  trace（含 2.0 的 BMA/turn_router + 按缓存折扣算真实费）才能定论——**别只拿冷启单轮下结论**。

## 二·补2：接 OTel collector 摄入 2.0 逐 generation token → 结论彻底翻转（definitive）

**动作**：集群内起 OTel collector(`otel/opentelemetry-collector-contrib`，OTLP:4318 收 → prometheus:8889 暴露)，
给 2.0 三进程(bma/ca2-mainagent/workflows)配 `OTEL_METRICS_ENABLED=true` + `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`
(chatagent core.observability 记 `gen_ai.client.token.usage`，`gen_ai.token.type∈{input,output,cache_read}`)。
每用例 curl collector 前后差值 = 2.0 该轮**完整** token；2.3 用前门 SSE usage(单 agent 全量)。

**发现前门 SSE 把 2.0 漏报 ~10x**：一个 shops 轮 2.0 其实跑 **5 个 agent**——bma_classify(input 1805)+
bma_turn_router(1594)+conversation_speaker(1753)+projectterm_resolver(4872)+**searchshops_collect_v2(14705)**，
合计 input 24,729；而前门 usage 只捞到 conversation_speaker 的 1753。

**多轮·切业务·完整账(5 用例合计 fresh=input-cache_read)**：**2.0=104,688 vs 2.3=59,062 → 2.3/2.0=0.56x**
（switch_long 6 轮：2.0 fresh 34,741 vs 2.3 10,128）。命中率 2.0 36–78% / 2.3 84–94%。时延多轮均值
2.0 24.2s→2.3 21.2s(2.3 略快)。**先前"2.3 贵 5–8x/更慢"彻底证伪**——那是 2.0 被漏报造出来的。
机制：2.3 单 agent 恒定前缀，多轮/切业务一路高命中；2.0 在 5 个不同 prompt 的 agent 间跳、切业务换 collect，
缓存碎片化。**诚实边界**：0.56x 是全价 fresh 口径；2.3 读 3.3x 更多缓存(638k vs 194k)，**盈亏平衡 d≈10.3%**——
缓存折扣 ≤10% 则 2.3 更省/持平，偏高(20–40%)则 2.0 更省。**结论：同一量级，谁更省取决于缓存定价，非某方碾压。**

EDD 新增/复用：`compare_multiturn.py`(cache/非cache 分账) + collector 摄入脚本 + token 分账评估器
(InputTokens/CacheReadTokens/FreshTokens/CacheHitRate，TDD)。这落了 spec 待办#3(Langfuse/trace 摄入)的核心。

## 三、被评系统侧的坑（非 EDD，但部署时踩到，记录备查）

- chatagent3 DBOS on SQLite 有 `application_versions.version_timestamp` NOT NULL 迁移 bug →
  改用 Postgres(`DBOS_SYSTEM_DATABASE_URL=postgresql://...`)。
- chatagent3 toolexecutor 控制 API(:8310，mainagent 靠它 start_or_attach 起工具 workflow)
  **仅当配了 `TE_REGISTRY_DATABASE_URL` 才启动**——不能为省库而留空。
- chatagent2 MySQL(interrupt_store/会话历史，root/root/db=sessionstore) 是启动硬依赖。
- mock datamanager 需两处补丁：绑 `0.0.0.0`(k8s 跨 pod)、`combinedQuery` 返回键
  `commercials`→`commercialActivities`(否则 searchcoupons 恒 0)。它服务的 2.0 路径正好齐全：
  `/shop/workflows/complexQuery`、`/activity/workflows/combinedQuery`、`/package/listTreePage`。
- **2.0 完整前门 = 5 进程**：orchestrator@2.0(:7100) + workflows(单进程跑 Temporal worker
  `chat-turn-workers` + FastAPI :8200) + **BMA/business_map_agent 是独立 HTTP 服务(:8103，
  `/classify`+`/turn_router/*`)**，不是 chatagent2 里的一个 agent_type——workflows 每轮先 HTTP 调
  BMA classify 路由。BMA 用 `LITELLM_BASE_URL`+`LITELLM_KEY_BMA_{SLM,LLM}`(模型 qwen3.5-flash /
  deepseek-v4-flash)。
- workflows 直连 MySQL 库名 **`orchestrator`**（非 chatagent2 的 `sessionstore`）写
  `session_search_history` 等 4 张表——须**预建库+载 `sqls/schema.sql`**；写 fail-soft 但 `agent_message_pending`
  在正常轮路径上，别省。三仓的 nacos.py 默认 `USE_NACOS=TRUE`/`ACTIVE=test`，本机必须显式
  `USE_NACOS=FALSE`+`ACTIVE=local` 否则启动去连 Nacos。
- searchshops/searchcoupons 的地名→坐标要 `ADDRESS_SERVICE_URL`(:8092 `/api/address/geocode`)，
  本环境无此后端；用例带 `current_location` 坐标时不触发，触发则该次搜索降级。置占位避免 import 报错。

## 四、EDD 仍待改进（后续）

1. **基础服务多库支持**：本轮把 sessionstore/DBOS/te_registry 三份表挤进同一个 PG 库绕过。
   `postgres` 只认单个 `POSTGRES_DB`；应支持初始化多库(initdb 脚本/多 `BaseService` 声明)。
2. ~~**前门入口适配器**~~ ✅ **已落地**(见 §一 #12)：`frontdoor.py` 经前门 `/chat/stream`
   驱动完整一轮 + 聚合 SSE。**待泛化进 EDD 核心**：目前是 example 胶水(打 orchestrator :7100)；
   应升为 SystemVersion 级"入口适配器"声明(送入端点/契约、读输出方式、同步或异步/SSE/poll)，让
   任意被评系统声明式接前门，而非每个项目手写 target。
3. **Langfuse trace 摄入**：当前工具轨迹/token 从 /chat/run 响应直读；TTFT 等要靠被评系统
   emit OTel → Langfuse。应把 EDD 评估上下文接上 Langfuse trace(OTLP 摄入 + 按 run/用例过滤)。
4. **依赖顺序/就绪门控**：K8sProvider 目前一把 apply 后按序等 rollout；基础服务(kafka/pg/
   temporal)应先就绪再起业务进程，减少 CrashLoop 抖动。
5. **build 产物缓存/复用**：同分支重复 build 应可跳过；`image_ref` 已稳定，可加 digest 校验。
