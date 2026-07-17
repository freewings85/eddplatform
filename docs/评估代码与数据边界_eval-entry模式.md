# 评估架构（定死）：EDD 管理 + 调度，逻辑 = git 里的 Temporal workflow

> 本文档锁定 EddPlatform 里"评估由谁写、住在哪、平台管什么、怎么触发"这条架构线。
> 结论是在走通 **自定义评估器、每用例参数、trace 导入、HITL 暂停恢复** 几个硬案例、并做了大幅化简后收敛出来的，作为后续实现与原型的准绳。

## 结论（一句话）

**EDD = 用例的管理 + 调度；用例的真逻辑 = git eval 项目里的 Temporal workflow**（标准 pydantic-evals 代码，用 `TemporalAgent` 跑成 durable workflow）。
约定：eval 项目提供**一条启动命令**起一个 **worker**，worker 上注册**一个通用 workflow（`RunCase`）+ 一张按 `code` 的实现表**；**平台(EDD) 只用 Temporal client**，按 `code` 触发（`code` 走参数、workflow-id 带 `code`）、收一份**扁平 JSON**。
平台**不碰文件 / 依赖 / 部署，也不校验逻辑** —— 连"代码文件路径"都不存，绑定靠命名约定。

## 一、用例（平台侧登记项）

一个用例 = ：

| 组成 | 说明 |
|---|---|
| `code` | 唯一编号；触发时走参数 + 进 workflow-id，也是结果对回来的接缝 |
| **说明** | ① yaml 式结构描述（inputs / 期望 / 元数据，可选）+ ② 一段纯文字描述；可选**关联一条 trace** |
| **状态** | 待实现 / 已实现（eval 项目的实现表里有没有这个 `code`） |

管理元数据（驱动外环）：需求标签（→ 需求达标卷积）、适用系统版本（→ 跨版本对比公平性）、Dataset 分组、启用 / 归档。

**生命周期**：新建时只填 `code` + 说明 → 开发者在 eval 项目里**按 `code` 注册这条用例的实现**（一个 handler）→ 状态转「已实现」。
**没有"代码文件路径"了** —— 用例和实现的绑定靠 `code`：eval 项目按 `code` 登记实现，平台按 `code` 触发。不靠硬文件。

## 二、eval 项目（git）提供什么

1. **启动命令** —— 一条 EDD 能调的命令，在沙箱里**起一个 worker**（连 Temporal、poll task queue、托管 workflow）。形如 `evalctl serve --task-queue evals`。**起 worker 是它的活，不是平台的。**
2. **一个通用 workflow（`RunCase`）+ 一张按 `code` 分派的实现表** —— 注册在 worker 上；worker 带依赖、带对被评系统的访问。

eval 项目**可以就是被评系统的主代码库，也可以是独立评估库**（同库 in-process 自测 / 独立库前门对比）。这些对平台都是解耦的 —— 平台只用 client 按 `code` 触发。

## 三、执行 = 触发 Temporal workflow

**启动一个 Experiment（= 一个 Dataset × 一个系统版本 × 沙箱）的序列：**

1. **拉 ref** —— checkout eval 项目那个钉住的 ref。**这一步就是"尺子钉死"的物理动作**（ref 定 = 评估逻辑 + 依赖 + rubric 全定）。
2. **起 worker**【eval 项目侧】—— 在沙箱里运行 eval 项目的启动命令，把通用 `RunCase` + 按 `code` 的实现表注册到 worker、连上一个 task queue（按 run 隔离）。
3. **逐 code 触发**【平台侧 · 只用 client】—— 遍历 Dataset 选中的 case：`client.execute_workflow("RunCase", {code, target}, id=f"exp/{code}")`，`target` = 版本 × 沙箱。可**并发**触发：某条 HITL 用例 durable 等 signal（等 3 天）**不阻塞整批**。
4. **收结果**【平台侧】—— 每个 workflow 回吐扁平 JSON，按 `code` 收回 → 汇成这个 Experiment 的 Report + 逐 case 结果。

第 ② 步在 **eval 项目侧（worker）**，第 ③④ 步在 **平台侧（client）**。触发时实现表里没有这个 `code`（用例还"待实现"）→ **fail loud**，不静默。编排（遍历 + 触发 + 收）就是平台一段 client 代码；要更强的持久化，这段本身也可包成一个 Temporal workflow。

- 用例逻辑（driving 系统、评估器、判定）全在 workflow 里，标准 pydantic-evals；model / tool 调用是 Temporal activity。
- **HITL = Temporal 原生**：商家报价 / 人审批 = 给运行中的 workflow 发一个 **signal**，workflow **durable 地等**（等 3 天不占进程）。暂停 / 恢复 / 等待全归 Temporal —— 不再手写 resume 循环。
- **对比（Comparison）= 同一套动作跑两遍**：v1、v2 各一个 Experiment，但用**同一个 eval 项目 ref 起的 worker**（同一批 workflow 代码）→ 同一把尺子，两版才可比。

## 四、平台不做对齐（故意）

平台**不校验**说明 ↔ 代码是否一致。代码是唯一真相，说明只供管理，漂移**不可见、可接受**。
→ 砍掉了一整摊复杂度：评估器当数据存（EvaluatorDef / params）、内置 vs 自定义分档、schema 双向校验、"引用一把没写的尺子再等回填"的 handoff —— 全不需要。平台不再假装懂评估。

## 五、输出 JSON 规范（(子)workflow ↔ 平台唯一硬接口）

每个（子）workflow 返回一份**扁平** JSON。这是平台做管理 / 对比 / 卷需求的**全部依据**。

**骨架（固定两个字段）：**

```json
{ "code": "CASE-砍价-预算", "passed": false, "...": "用例自定义的扁平字段" }
```

- `code` —— 哪条用例，平台靠它把结果对回去。
- `passed` —— 总判定（bool），平台卷"需求达标"**只认它**。

**其余字段用例自己定，但强制一层（scalar）**，按类型定角色（同 pydantic-evals）：`bool → 判定 / 数值 → 分数 / 字符串 → 标签`。平台照类型画列、跨版本比、聚合，**不用懂字段语义**。**禁止嵌套、禁止对象数组**（"每轮报价"压成 `砍价轮数: 3`）。父 workflow 把子 workflow 的这些结果汇总。

## 六、尺子一致性 = 钉 ref

跨版本对比要求两版用**同一把尺子** —— 做法是一次 Comparison 里 v1、v2 跑**同一个 eval 项目 ref 部署的 worker**（同一批 workflow 代码 + 依赖）。钉一个 ref = 评估逻辑 + 依赖 + rubric 全钉死。单版本自测则无所谓。

## 七、评估器概念在平台侧退化

因为逻辑全在 workflow 代码里，平台**不建评估器模型**（无 EvaluatorDef、不存参数、不分内置 / 自定义档）。
评估器只是 workflow 代码里用到的东西 —— 现成的 pydantic-evals 内置（`EqualsExpected` / `ToolCorrectness` / `TrajectoryMatch` / `LLMJudge` / `GEval`…）或自己写的 `Evaluator` 子类。**平台一律不感知，只收扁平 JSON。**

## workflow 形态示例

```python
# eval 项目：一个通用 workflow，按 code 分派到该用例的实现
@workflow.defn(name="RunCase")
class RunCase:
    @workflow.run
    async def run(self, args) -> dict:
        return await CASE_HANDLERS[args["code"]](args["code"], args["target"])

# 某条用例的实现（HITL：商家报价靠 signal 喂进来，durable 等，反应式，不是磁带）
async def haggle_budget(code, target) -> dict:
    deal = await negotiate(goal="买二手相机", budget=900, merchant=reactive_merchant())
    return {                                    # ← 扁平 JSON（骨架 + 自定义 scalar）
        "code": code, "passed": deal.closed and deal.price <= 900,
        "成交价": deal.price, "低于预算": deal.price <= 900, "砍价轮数": deal.rounds,
    }
CASE_HANDLERS = {"CASE-砍价-预算": haggle_budget}   # eval 项目按 code 登记实现
```

```python
# 平台(EDD)：只用 client，按 code 触发 + 收。没有 Worker。
client = await Client.connect("temporal-server:7233")
for code in dataset:
    results[code] = await client.execute_workflow(
        "RunCase", {"code": code, "target": target}, id=f"exp/{code}", task_queue="evals")
```

平台侧只存：`code=CASE-砍价-预算`、说明（+ 可选 trace 链接）、状态=已实现、需求标签。
EDD 按 `code` 触发 → 收扁平 JSON → 靠 `code` 对回平台那条用例。**平台不知道、也不需要知道实现在哪。**
