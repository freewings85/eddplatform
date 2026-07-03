# 用 AI 工具提升 AI 业务整体研发效率：调研报告与落地方案

> 版本 v1.0 ｜ 日期 2026-06-30 ｜ 负责人：AI 团队开发负责人
> 配套设计文档：`docs/superpowers/specs/2026-06-30-ai研发提效调研-design.md`
> 证据来源：两轮 deep research（联网检索 + 对抗式交叉验证），来源清单见文末附录。

---

## 摘要（给决策层）

**命题**：我们团队要在汽车服务领域批量产出业务 Agent（保险、服务报价、门店查询、项目推荐、智能客服、预约引导……）。效率的瓶颈不是"某个人写代码慢"，而是**缺一套"标准化 + 复用 + AI 辅助"的研发体系**，让整支团队又快又一致地造这些业务 Agent。

**四条核心结论**：

1. **AI 工具能提效，但不是自动提效，必须靠规范和护栏"工程化"出来。** 业界最硬的反例（METR 2025 RCT）显示：资深开发者在熟悉的成熟代码库里用早期 2025 AI 工具反而**慢了 19%**，却自评"快了 20%"。〔1〕〔2〕Google DORA 2025 也发现 AI 与交付吞吐量转正、但**与交付稳定性仍负相关**〔5〕。结论：**别信自我感觉，要用客观指标度量；要靠 eval / review / CI 护栏把"快"转成"净效率"。**

2. **我们差异化的效率杠杆是"复用底座 + eval 驱动开发"，而不是编码助手本身。** 对非确定性的 Agent 系统，最有据可循的质量与迭代杠杆是 **eval 驱动开发**〔6〕〔7〕；而 pydantic-ai 生态已经把 eval（Pydantic Evals）和可观测（内置 OpenTelemetry → Logfire / Langfuse）做成了**一方/开源现成能力**〔8〕〔9〕，我们直接复用即可，不用自建。

3. **平台层的 build-vs-buy 答案是"分层混合"：基础设施尽量买/复用开源，自研力量集中在业务差异化层。** pydantic-ai 是无状态的 Agent SDK，**编排 + 持久化执行（durable execution）是独立的一层，属于"应买不应造"的专用基础设施**〔10〕〔11〕。"自研 Agent OS"只在"多业务线 + 多团队 + 要多租户/治理"时才划算，且应像 Salesforce BYOP 那样"共享基础设施建一次、各业务自带推理引擎"〔12〕。

4. **度量要实事求是、反虚荣、不考核个人。** 用 DX Core 4（统一 DORA/SPACE/DevEx 的速度/有效性/质量/业务影响四维）建基线〔13〕，AI 工具专项用"采纳/影响/成本"三维并以"每人每周节省工时 + 间接指标"衡量价值〔14〕；**绝不把这些指标用于个人绩效考核，速度指标必须配对冲指标**〔15〕。

**一句话路线建议**：**编码助手谨慎试点 + eval 驱动开发立规范 + 复用 pydantic-ai 一方 eval/可观测 + 编排/持久化复用开源 + Agent OS 平台分阶段薄自研 + 用 DX Core 4 度量。**

---

## 0. 问题定义与效率观

### 0.1 真实命题
> 如何给团队建立一套"标准化 + 高效率"的 AI 研发规范与支撑系统（可基于开源、也可自研），让整支团队能又快又一致地批量产出汽车服务的各业务线 Agent。

### 0.2 效率的三个杠杆
- **标准化**：规范 / 模板 / 脚手架 / golden path —— 让每条业务线"按同一套路造"。
- **复用**：共享底座与组件（tools / skills / memory / workflow / 业务语义）—— 业务线越多，复用的边际收益越大。
- **AI 辅助研发**：用 agentic 工具更快地造 agent（"递归"效应）—— 但收益有条件，见下。

### 0.3 什么才算"效率提升"（直接对接公司"指标"）
**反对单一指标和虚荣指标**（代码行数、AI 接受率、commit 数、PR 数）。开发者生产力是多维的——SPACE 框架把它分解为满意度、绩效、活动、协作、效率/心流五维，明确"不能用单一指标衡量"〔3〕。值得注意的是，2026 年已有批评指出：当 AI 大量生成代码时，SPACE 里的"活动(Activity)"维度会变得更具误导性——这恰恰反证了"别用产出量当效率"的论点。
**度量主框架用 DX Core 4 + DORA**，详见第 5 部分。

---

## 1. 业界证据与方法论（实事求是版）

### 1.1 AI 编码助手：收益真实但有边界，且自评不可信

**反例（必须正视）**：METR 2025 年的随机对照试验（RCT）——16 名平均 5 年经验的资深开源开发者，在自己熟悉的成熟大仓（平均 22k+ star、100 万+ 行）里完成 246 个真实 issue，随机分配"允许/不允许用 AI"。结果：**允许用 AI 反而慢了 19%**。更关键的认知差：开发者**事前预测会加速 24%，亲历变慢后仍自评加速了 20%**〔1〕〔2〕。

**边界条件（别误读为"AI 没用"）**：这个结论严格限定于"**资深开发者 + 熟悉的成熟代码库 + 早期 2025 工具（Cursor Pro + Claude 3.5/3.7）**"。作者明确不向新手、陌生代码库、或数百小时熟练后外推。METR 2026-02 的跟进实验对新招募开发者只估出约 -4%（置信区间跨 0），并自评原指标"可能是个不好的代理"、正在重做实验〔16〕。

**对我们的含义**：
- 我们的主场景是"**中初级工程师 + 标准化脚手架 + 批量造新业务 Agent（偏新代码、重复度高）**"——这恰恰是 AI 收益**很可能为正**的场景，但**必须自己用小范围 A/B 验证**，不能假设。
- **对资深工程师在核心存量代码上的工作，不要盲目强推 AI 编码工具**，让其自主选择。
- **永远不要用"自我报告"衡量提效**——这是本研究给度量体系最硬的一条约束。

### 1.2 AI 加速会暴露下游薄弱点——必须配护栏

Google DORA 2025 报告：相比 2024，AI 采纳与"软件交付吞吐量、产品性能"的关系**由负转正**；但与**交付稳定性仍然负相关**——"AI 加速了开发，但这种加速会把下游的薄弱点暴露出来"〔5〕。（2024 版曾估算：AI 采纳度每升 25%，吞吐降约 1.5%、稳定性降约 7.2%〔17〕。）

**含义**：AI 提速本身不等于净效率提升。**把"快"转化为"净效率"的，是标准化的 review / eval / CI 护栏**。这是第 2 部分"规范"和第 3 部分"eval 工具链"的根本理由。

此外，2026 年研究表明：**agent 生成的代码比人写代码冗余更多、单次变更引入的技术债更高**——同行评审研究（MSR 2026 录用）指出 LLM agent "经常忽视代码复用机会、导致冗余高于人类开发者"〔18〕〔19〕。所以**显式的 code review 标准对非确定性/agent 代码是必需品，不是可选项**。

### 1.3 Eval 驱动开发：非确定性系统的"新单元测试"

对 Agent/LLM 系统，最有据可循的迭代方法论是 **eval 驱动开发**（Hamel Husain & Shreya Shankar，2026-01 更新的权威实践 FAQ）〔6〕：

- **错误分析是 eval 里最重要的活动**：对**真实 trace** 做人工错误分析，看 ≥100 条，约 20 条无新错即"理论饱和"。
- **优先二元 pass/fail，而非 Likert 量表**：量表需要更大样本才能检出差异，且标注者爱选中间值。
- **拒绝通用预制指标**（如 helpfulness / coherence）：你不知道它在测什么、是否对应你的业务成功；它们只制造"虚假的信心"。（可作探索/分诊用，但不能当成功指标。）
- **别追高通过率**：100% 通过往往说明题太简单；~70% 才说明 eval 在真正压测系统。（这是经验法则，非统计阈值。）

**LLM-as-judge 两大坑**（UIST 2024《Who Validates the Validators》）〔7〕：
1. **judge 会继承被测模型的缺陷**——"谁来验证验证者"，必须用**人工标注校准** judge。
2. **评判标准事先定义不出来、要在看输出过程中演化**（作者称 "criteria drift"）——所以 eval 标准是**活的工件**，不是一次性写死的规格。

---

## 2. 标准化研发规范（核心交付物 · 可直接落地的团队 SOP）

> 这一节是"给团队的那套规范"。原则：**先固化流程与复用，再叠加 AI**；AI 在每个阶段是"加速器"，不是"免检通道"。

### 2.1 AI-native SDLC：造一条业务 Agent 的标准流水线

```
需求/意图定义
  → prompt & 上下文工程（按规范）
  → 工具/技能封装（优先复用共享库）
  → 构造 eval 数据集（来自真实 trace / 历史工单）
  → 实现（AI 编码助手加速，但守 review 标准）
  → 评测（Pydantic Evals 跑回归，达门槛才放行）
  → 灰度发布（按用户/比例/白名单）
  → 线上可观测（OTel trace → Logfire/Langfuse）
  → 错误分析 → 回灌 eval 数据集 → 迭代
```

每个阶段的规范要点：

| 阶段 | 规范要点 | 备注 |
|---|---|---|
| 需求/意图 | 统一意图定义模板；明确成功标准（可被 eval 检验） | 成功标准要可量化 |
| Prompt/上下文工程 | 统一 system prompt 结构、上下文装配规范、版本化管理 | "最小高信号 token 集"原则 |
| 工具/技能封装 | **先查共享库再造**；工具原子化、强类型 I/O（pydantic-ai 天然支持） | 复用率是关键指标 |
| Eval 数据集 | 来自真实 trace/历史工单；二元标注；标准随输出演化 | 见 1.3 |
| 实现 | AI 助手加速；资深者自主、新人按 golden path | 见 1.1 边界 |
| 评测 | Pydantic Evals 入 CI；不达门槛不放行 | 见第 3 部分 |
| 灰度 | 按用户维度/比例/白名单分流 | 与现有运维规划对齐 |
| 可观测 | 一律 OTel；trace 必采 | 见第 3 部分 |
| 迭代 | 错误分析 → 回灌 eval | 闭环 |

### 2.2 跨业务线复用机制（业务线越多，价值越大）

有立场论文论证：**企业级 agentic 开发的瓶颈是"知识架构"而非模型能力**——把机构知识重构为机器可消费的单元（"AI Skills"），这样的组织会跑赢只投模型能力的组织〔20〕。
> ⚠️ 该论文为非同行评审、单作者的立场文章（推广其自有框架），请按"一种主张/视角"引用，不作既定事实；其"知识图谱"等具体子主张未通过本研究验证。

落到我们的做法（**这与你们 Agent OS 规划里的 ontology/记忆/技能复用一脉相承**）：

- **共享工具库（Tools）**：原子化、强类型、可注册/可审计——一次封装，多业务线复用。
- **共享技能/工作流库（Skills/Workflow）**：把"怎么做某类任务"沉淀为可复用单元。
- **共享记忆与业务语义（Memory/Ontology）**：用户、车辆、门店、服务项目、优惠、订单、工单等统一建模，让各业务 Agent 复用同一套语义。
- **标准脚手架**：基于 pydantic-ai 的项目模板（统一目录、配置、eval/trace 接线、CI），新业务线"克隆即起步"。
  > ⚠️ "标准脚手架/golden path 的具体模板"在本研究中缺乏可直接引用的业界范本（属残留缺口，见 §6.3）；建议我们**自己沉淀一份内部模板**作为团队 golden path。

### 2.3 内部 golden path（黄金路径）

平台工程界的 "golden path / 黄金路径" 概念：为团队提供**一条铺好的、自助的、默认正确的标准路径**，降低认知负担、让"做对"成为最省力的选择〔21〕。
对我们：把 2.1 的流水线 + 2.2 的复用库 + 2.4 的 review 标准，封装成"新建一条业务 Agent 时默认走的那条路"。**golden path 是规范能否真正落地的关键**——规范靠文档推不动，靠"默认路径最省事"才推得动。

### 2.4 非确定性系统的测试与 Code Review 标准

- **测试**：以 eval 套件为主（见 1.3 / 第 3 部分），入 CI 做回归；确定性部分（格式/PII/正则）用代码校验，主观质量用 LLM-judge（须人工校准）。
- **Code Review**（针对 AI/agent 生成代码，见 1.2）：
  - 显式检查**冗余与重复**（agent 代码的已知弱点）——优先复用而非新造。
  - 检查是否引入隐性技术债（过度生成、不必要抽象）。
  - AI 生成代码与人写代码同等 review 标准，**不因"AI 写的"而降低门槛**。

### 2.5 AI 编码 agent（Claude Code / Cursor）如何安全嵌入

- **新人/新业务（偏新代码、重复度高）**：纳入 golden path，鼓励使用 + 配套规范（提示规范、review 守门）。
- **资深/核心存量代码**：自主选择，**不强推**（见 METR 边界）。
- **统一约定**：用规则文件（如 `CLAUDE.md`/项目规则）、共享 skills、子代理等把"团队规范"喂给编码 agent，让 AI 按我们的规范干活。
- **务必度量、不靠感觉**：用小范围 A/B（见第 5 部分）验证每类场景的真实收益。

---

## 3. 工具链选型（围绕 pydantic-ai）

> 总原则：**底层基础设施尽量复用一方/开源，自研力量留给业务差异化层。**

### 3.1 分层视图

| 层 | 选型建议 | 理由/证据 |
|---|---|---|
| 模型层（LLM） | 买（API） | 无争议 |
| **Agent SDK** | **pydantic-ai（已锁定）** | 类型安全、无状态、Agent 即强类型 Python 对象〔10〕 |
| **Eval** | **Pydantic Evals（一方，代码优先、可进 git）** | 含确定性校验 + LLM-judge；datasets/cases/evaluators 全在 Python 定义〔8〕 |
| **可观测/Trace** | **内置 OpenTelemetry → Logfire（一方）或 Langfuse（开源）** | `instrument=True` 即出 OTel span，后端可换、不锁定〔9〕 |
| **编排 + 持久化执行** | **复用开源**：Temporal / DBOS / Prefect / Restate（pydantic-ai 官方集成）或 LangGraph（自带 Checkpointer） | "应买不应造"的专用基础设施，见 3.3 |
| 共享平台 / "Agent OS" | **分阶段薄自研**（多租户/批量/治理触发时） | 见第 4 部分 |
| AI 编码/研发助手 | Claude Code / Cursor / Copilot（试点） | 见 1.1 边界 + 2.5 |

### 3.2 Eval 与可观测：直接复用 pydantic-ai 一方能力

- **Pydantic Evals**：pydantic 团队出的一方评测框架，覆盖"单次 LLM 调用 → 多 Agent 应用"；**代码优先**（Dataset/Case/Evaluator 全用 Python 定义、可版本化、可进 git，区别于纯 Web 配置平台）；内置确定性校验器（正则/格式/PII）和 **LLMJudge**（评准确性、精/召、幻觉等主观质量）〔8〕。
- **可观测**：pydantic-ai **内置 OpenTelemetry**（`instrument=True` / `Agent.instrument_all()`），按 GenAI 语义约定导出 trace span，**原生接 Logfire**（一方，Web 端可视化/对比 eval 结果），也能接 **Langfuse 或任意 OTel 后端**，无需胶水代码〔9〕。
  - 模式：**代码定义 eval / Web UI 看结果**，trace 标准化一次（OTel）即后端可移植，**降低锁定风险**。
  > 注：成本参考——Logfire 按 span 计费（约 $2/百万 span，含免费档），可作选型参考但属 vendor 报价，以官网为准。

**结论**：eval 和可观测这两层，**复用一方/开源现成能力，不要自建**。这是 build-vs-buy 里最清晰的"buy/reuse"。

### 3.3 编排 + 持久化执行：这是独立的一层，应"买/复用"

**关键认知**：pydantic-ai 是**无状态的 Agent SDK**——它本身**不提供持久化、不提供 durable execution**，而是把这些委托给外部引擎〔10〕。所以"编排 + 持久化执行"是**和 Agent SDK 不同的另一层**，不要指望框架自带。

**Durable execution 是公认的"应买不应造"问题**——它要解决：API 超时/进程崩溃后从中断处**精确续跑**、状态持久化、以及 human-in-the-loop **长时挂起（hours/days 后精确恢复）**。Temporal 官方（与 pydantic 共建集成）直言："有些问题用专用工具比自己造更好，durable execution 就是其中之一"〔11〕。pydantic-ai 官方共维护 **Temporal / DBOS / Prefect / Restate** 四个集成，把模型/工具/MCP 调用封装成可重放、可 checkpoint 的 durable step〔10〕〔11〕。

**两条可选路线**：
- **A. pydantic-ai + 专用 durable execution 引擎**（Temporal/DBOS/Prefect/Restate 之一）：保留 pydantic-ai 的类型安全，把"可靠续跑/长时挂起"交给成熟引擎。**推荐作为我们的默认路线**（与已锁定的 pydantic-ai 最契合）。
- **B. LangGraph**：自带 Checkpointer，在每个 node 后快照图状态，崩溃/暂停后从最近 checkpoint 续跑、支持 HITL——是另一种"有状态图/状态机编排"路径〔10〕。与 pydantic-ai 是**不同定位、可互补**，但引入它意味着多一套编排心智，需评估是否值得。

> ⚠️ 残留缺口：研究问题点名的 **Dify / CrewAI / AutoGen / Prefect 的细分定位**在本轮没有独立验证证据（见 §6.3）。按业界通识：Dify 偏"低代码 LLM 应用平台"（适合快速搭、非深度定制）、CrewAI/AutoGen 偏"多 Agent 协作编排"。**若要把它们写进正式选型，建议再补一轮针对性调研**，本报告对这几个不下确定结论。

### 3.4 选型小结（围绕 pydantic-ai 的推荐栈）

```
LLM API
  └ pydantic-ai（Agent SDK，已锁定）
      ├ Pydantic Evals（评测，一方）
      ├ OpenTelemetry → Logfire / Langfuse（可观测，一方/开源）
      └ Temporal / DBOS / Prefect / Restate（持久化执行，开源，按需引入）
  〔上层〕共享工具/技能/记忆/语义库 + 标准脚手架（自研，差异化）
  〔再上层〕Agent OS 平台（多租户/批量/治理触发时，分阶段薄自研）
```

---

## 4. Build-vs-Buy：开源还是自研？

### 4.1 决策框架：分层混合（不是二选一）

**不要在"全开源 vs 全自研"之间二选一，而是分层决策**：

| 层 | 决策 | 说明 |
|---|---|---|
| 模型 | **买** | API |
| Agent SDK | **复用开源（已选 pydantic-ai）** | ✓ |
| Eval / 可观测 | **复用一方/开源** | Pydantic Evals + OTel/Logfire/Langfuse |
| 编排 / 持久化执行 | **复用开源** | Temporal 等；"应买不应造"〔11〕 |
| 共享底座（工具/技能/记忆/业务语义） | **自研** | 这是差异化所在 |
| Agent OS 平台（多租户/批量/治理） | **分阶段薄自研** | 见 4.2 |
| 各业务线 Agent | **自研** | 业务价值所在 |

**一句话**：**把"通用且难做的基础设施"买/复用，把"自研力量集中在业务语义与复用底座"这些别人替代不了的层。**

### 4.2 什么时候才该自研 "Agent OS" 平台？

**参考范式：Salesforce BYOP（Bring Your Own Planner）**〔12〕——一个多租户 Agent 平台，**只把共享基础设施建一次**（会话管理、状态持久化/durable execution、streaming、工具调用、企业数据集成、多租户），让各业务团队**"自带推理引擎"**，从而既要团队自治、又不重复造轮子。支撑 7,000+ 日活会话、服务 100+ 工程师。
> ⚠️ 单公司 n=1 案例，且其"多租户隔离的具体实现机制"子主张未通过验证——可借鉴**架构范式**，但不要照搬其隔离实现细节。

**自研触发条件（我的建议判断标准，非验证证据，供讨论）**：当**同时**满足以下多数项时，自建共享平台才划算——
- 业务线数量达到一定规模（多条线在重复造同样的会话/状态/工具接入）；
- 多团队并行开发、需要团队自治 + 统一治理；
- 需要多租户隔离、统一安全治理与审计（你们 plan.txt 里权重很高的部分）；
- 批量生产业务 Agent 已成常态。

**关键原则**：**晚做、薄做、共享建一次**。先用"pydantic-ai + 开源编排 + 一方 eval/可观测 + 自研共享库"把前几条业务线跑顺、把复用模式验证清楚；当重复成本明显 > 自建成本时，再把已验证的共享能力沉淀为平台。**这恰好对应你们 Agent OS 规划的初→中→高级演进路径**，本报告为该路径提供了"先复用、按阈值再自建"的决策依据。

> ⚠️ 残留缺口：从"复用开源编排"跨越到"自研 Agent OS"的**量化触发阈值**（具体多少业务线/租户/并发会话才划算），业界没有现成公式（见 §6.3）。建议我们结合自身重复成本测算自定阈值。

---

## 5. 度量与汇报（回应公司"指标"）

### 5.1 度量主框架：DX Core 4 + DORA

- **DX Core 4**：把 DORA、SPACE、DevEx 统一为**四个相互制衡(counterbalanced)的维度——速度 / 有效性 / 质量 / 业务影响**〔13〕。"相互制衡"意味着：一个维度变好可能让另一个变差，所以**必须组合看，不能单看一个**。该框架由 DORA/SPACE 原作者（Forsgren 等）共建。
- **DORA 四指标 + 第五指标 Reliability**：部署频率、变更前置时间、变更失败率、恢复时间、可靠性；可参照 Elite→Low 分层阈值定位现状〔13〕。
  > 注：分层阈值为 2019 版（Elite=多次/日部署、<1天前置、0–15% 失败率、<1小时恢复），后续报告聚类有演进，作参照不作硬标准。

### 5.2 AI 工具专项度量：DX AI 三维

用 **采纳(Utilization) / 影响(Impact) / 成本(Cost)** 三维〔14〕：
- **不要只看采纳率/使用量**——"采纳只是开始，真正的价值来自用数据看影响"。
- **影响用结果指标**：如"每人每周节省工时" + DX Core 4 间接指标（PR 吞吐、感知交付速率、Developer Experience Index、质量/可维护性）。

### 5.3 我们这个场景的结果指标（建议）

针对"批量产出业务 Agent"，建议跟踪：
- **新业务线 time-to-launch**：从需求到灰度上线的周期（最能体现"多业务线提效"）。
- **eval 通过率趋势 / 回归不退化率**：质量门（注意 ~70% 才说明 eval 在压测，见 1.3）。
- **复用率**：新业务复用既有 tools/skills/workflow 的比例（复用是核心杠杆）。
- **AI 工具采纳 + 留存 + 每周节省工时**：活跃使用而非一次性试用。
- **DORA 四/五指标**：尤其盯**稳定性**（AI 提速的已知风险，见 1.2）。
> ⚠️ 这些结果指标的"具体计算口径/落地细则"业界无统一范本（见 §6.3），需我们自定义并在试点中校准。

### 5.4 反虚荣 / 反滥用护栏（关键，直接服务向高管汇报）〔15〕

- **绝不用于个人绩效考核**——DORA/DX 指标反映**团队能力**而非个人产出。
- **速度/吞吐类指标单用有害**，必须配对冲指标（如 Developer Experience Index）。
- **不对指标设目标或绑奖励**（防 Goodhart 式博弈、"恶意合规"）。
- **透明沟通**：度量服务于**组织投资决策**，不是微观管理。
- **永远不用自我报告当提效证据**（METR 已证自评与实测可相反，见 1.1）。

### 5.5 怎么快速建立基线
**数周内**可用"**调研自评数据 + 系统数据**"结合的方式起步：先用 survey 快速得到全局视图，同时并行推进系统数据采集——**不要等指标平台搭好才开始**〔22〕。
> 注：vendor（DX）来源，但与 Forsgren 共建并被多方印证；"数周得到的全局视图"主要来自调研，完整系统数据整合更久。

### 5.6 向高管汇报的建议结构
1. **现状基线**（DX Core 4 四维 + DORA 现状定位）；
2. **干预**（规范 + 复用底座 + AI 工具试点）；
3. **结果指标变化**（new business time-to-launch ↓、复用率 ↑、eval 通过率趋势、稳定性守住）；
4. **实事求是的反例与边界**（哪些场景 AI 提效、哪些没有——这反而增强可信度）；
5. **投资建议**（下一步该投哪层）。
> ⚠️ 可直接套用的"汇报模板"业界无现成范本（见 §6.3），上述为建议骨架。

---

## 6. 路线图与残留缺口

### 6.1 分阶段落地路线（对齐团队成熟度"部分在用但不统一"）

**阶段一 · 收敛与立规（0–1 季度）**
- 定下 golden path v1：基于 pydantic-ai 的标准脚手架 + eval/trace 接线 + CI。
- 立 **eval 驱动开发**规范（错误分析、二元标注、LLM-judge 人工校准）。
- 复用 Pydantic Evals + OTel/Logfire(或 Langfuse) 统一 eval 与可观测。
- 立 AI 生成代码的 **code review 标准**。
- 建度量基线（DX Core 4 调研自评 + 系统数据起步）。
- AI 编码工具**小范围 A/B 试点**（先新人/新业务场景）。

**阶段二 · 复用与规模化（1–3 季度）**
- 沉淀共享库：工具/技能/记忆/业务语义（与 ontology 对齐）。
- 引入开源**持久化执行**引擎（Temporal/DBOS 等之一），覆盖长流程/HITL。
- golden path v2：把复用库 + review 标准织进默认路径。
- 度量转向结果指标（time-to-launch、复用率）。

**阶段三 · 平台化（按阈值触发）**
- 当多业务线/多团队/多租户/治理需求达阈值，按 BYOP 范式**薄自研 Agent OS**（共享基础设施建一次）。
- 对齐 plan.txt 的安全治理里程碑（沙箱、权限、审计、注入检测）。

### 6.2 安全治理（横切，对齐 plan.txt）
作为横切关注点贯穿各阶段：高危工具沙箱、工具调用权限/审批/审计、提示词注入/记忆注入检测、Agent 输入检测/上下文隔离/输出审查。规模化与平台化阶段重点建设。

### 6.3 残留缺口（建议后续补查的方向）
本报告已对核心决策点给出验证充分的结论；以下几处**证据较弱、本报告未下确定结论**，如要写进对外正式版建议再补一轮针对性调研：
1. **Dify / CrewAI / AutoGen / Prefect 的细分定位与适用边界**（§3.3）。
2. **标准化 Agent 脚手架 / golden path 的具体业界范本**（§2.2、§2.3）——建议先自沉淀内部模板。
3. **跨业务线复用的实证工程案例与复用率度量口径**（§2.2、§5.3，目前主要是理论锚点 + Salesforce 单案例）。
4. **"复用开源 → 自研 Agent OS" 的量化触发阈值**（§4.2）。
5. **向高管汇报的可套用模板**（§5.6）。

---

## 附录 A · 证据强度与时效说明

- **强证据（一手/多源交叉）**：METR RCT、DORA 2024/2025、SPACE、eval 驱动开发方法论、UIST 2024 judge 论文、pydantic-ai 的 eval/可观测/durable execution 集成（一手文档）。
- **中等证据（单源或 vendor，但作者权威/被印证）**：DX Core 4 及度量护栏（getdx.com，与 DORA 原作者共建）、Salesforce BYOP（单公司 n=1）、知识架构论文（非同行评审立场文）。
- **时效**：来源多为 2025–2026；AI 框架领域变化快，集成清单/能力会继续扩展。METR 结论限定早期 2025 工具与资深 OSS 人群，**不可外推**到新手/全体或更强的当前模型。
- **已剔除的不可靠子主张**（勿引用）：Salesforce 多租户隔离的具体实现机制；知识架构论文的"可运行时遍历知识图谱"；GitHub "1/5 review 涉及 agent、6000 万次 review" 的规模数字。

## 附录 B · 主要来源清单

1. METR《Measuring the Impact of Early-2025 AI on Experienced OS Developer Productivity》(blog, 2025-07-10) — https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/
2. 同上 arXiv 预印本 2507.09089 — https://arxiv.org/abs/2507.09089
3. SPACE 框架 (ACM Queue, 2021) — https://queue.acm.org/detail.cfm?id=3454124
5. DORA 2025 报告 (Google Cloud) — https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report
6. Hamel Husain & Shreya Shankar《AI Evals FAQ》(2026-01) — https://hamel.dev/blog/posts/evals-faq/
7. 《Who Validates the Validators?》(UIST 2024) — https://arxiv.org/abs/2404.12272
8. Pydantic Evals 官方文档 — https://pydantic.dev/docs/ai/evals/evals/ ｜ https://github.com/pydantic/pydantic-ai/blob/main/docs/evals.md
9. Langfuse × Pydantic AI 集成（OTel）— https://langfuse.com/integrations/frameworks/pydantic-ai
10. pydantic-ai Durable Execution 概览 — https://pydantic.dev/docs/ai/integrations/durable_execution/overview/ ｜ pydantic-ai vs LangGraph (ZenML) — https://www.zenml.io/blog/pydantic-ai-vs-langgraph
11. Temporal《Build Durable AI Agents with Pydantic AI》— https://temporal.io/blog/build-durable-ai-agents-pydantic-ai-and-temporal ｜ DBOS × pydantic-ai — https://docs.dbos.dev/integrations/pydantic-ai
12. Salesforce《Building a Multi-Tenant AI Agent Platform (BYOP)》— https://engineering.salesforce.com/building-a-multi-tenant-ai-agent-platform-handling-7k-sessions-without-cross-team-interference/
13. DX Core 4 / DORA metrics — https://getdx.com/research/measuring-developer-productivity-with-the-dx-core-4/ ｜ https://getdx.com/blog/dora-metrics/
14. DX《Measuring AI Code Assistants and Agents》— https://getdx.com/research/measuring-ai-code-assistants-and-agents/
16. METR Uplift Update (2026-02-24) — https://metr.org/blog/2026-02-24-uplift-update
17. DORA 2024 — https://dora.dev/research/2024
18. GitHub《Agent PRs Are Everywhere—How to Review Them》— https://github.blog/ai-and-ml/generative-ai/agent-pull-requests-are-everywhere-heres-how-to-review-them/
19. LLM 代码冗余研究 (MSR 2026) — https://arxiv.org/abs/2601.21276
20. 知识架构立场论文 (arXiv 2603.14805) — https://arxiv.org/abs/2603.14805
21. 平台工程 golden paths — https://platformengineering.org/blog/how-to-pave-golden-paths-that-actually-go-somewhere
22. DX Core 4（快速建基线）— https://getdx.com/research/measuring-developer-productivity-with-the-dx-core-4/
