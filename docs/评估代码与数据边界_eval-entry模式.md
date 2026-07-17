# 评估架构（定死）：EDD 管理 + 调度，逻辑 = git 里的 Temporal workflow

> 本文档锁定 EddPlatform 里"评估由谁写、住在哪、平台管什么、怎么触发"这条架构线。
> 结论是在走通 **自定义评估器、每用例参数、trace 导入、HITL 暂停恢复** 几个硬案例、并做了大幅化简后收敛出来的，作为后续实现与原型的准绳。

## 结论（一句话）

**EDD = 用例的管理 + 调度；用例的真逻辑 = git eval 项目里的 Temporal workflow**（标准 pydantic-evals 代码，用 `TemporalAgent` 跑成 durable workflow）。
约定：**workflow 名 = 用例的 `code`**。eval 项目**提供一条启动 workflow 的命令**、并把 workflow 注册在 Temporal worker 上；EDD 按 `code` **触发** workflow，收一份**扁平 JSON** 结果。
平台**不碰文件 / 依赖 / 部署，也不校验逻辑** —— 连"代码文件路径"都不存，绑定靠命名约定。

## 一、用例（平台侧登记项）

一个用例 = ：

| 组成 | 说明 |
|---|---|
| `code` | 唯一编号，**同时就是 workflow 名**；也是结果对回来的接缝 |
| **说明** | ① yaml 式结构描述（inputs / 期望 / 元数据，可选）+ ② 一段纯文字描述；可选**关联一条 trace** |
| **状态** | 待实现 / 已实现（eval 项目里有没有注册一个同名 workflow） |

管理元数据（驱动外环）：需求标签（→ 需求达标卷积）、适用系统版本（→ 跨版本对比公平性）、Dataset 分组、启用 / 归档。

**生命周期**：新建时只填 `code` + 说明 → 开发者在 eval 项目里注册一个**名字 = `code`** 的 workflow → 状态转「已实现」。
**没有"代码文件路径"了** —— 用例和实现的绑定靠**命名约定（workflow 名 = code）**，不靠硬文件。

## 二、eval 项目（git）提供什么

1. **启动命令** —— 一条 EDD 能调的命令，内部连 Temporal、按 `code` 触发对应 workflow（形如 `evalctl trigger --code <code> --target <版本/沙箱>`）。
2. **一批 workflow，名字 = 各用例的 `code`** —— 注册在 Temporal worker 上；worker 带依赖、带对被评系统的访问。

eval 项目**可以就是被评系统的主代码库，也可以是独立评估库**（同库 in-process 自测 / 独立库前门对比）。这些对平台都是解耦的 —— 平台只认"启动命令 + code 命名约定"。

## 三、执行 = 触发 Temporal workflow

执行一个用例 = **触发一个 workflow execution**（`id = eval-{run}-{code}`，`args = [case, target]`，`target` = 系统版本 × 沙箱）。

- 逻辑（driving 系统、评估器、判定）全在 workflow 里，标准 pydantic-evals；model / tool 调用是 Temporal activity。
- **HITL = Temporal 原生**：商家报价 / 人审批 = 给运行中的 workflow 发一个 **signal**，workflow **durable 地等**（等 3 天不占进程）。暂停 / 恢复 / 等待全归 Temporal —— 不再手写 resume 循环。
- **一次评估运行（Dataset × 版本）= 一个父 workflow**：fan-out 逐 case **子 workflow**（名 = 各 `code`），收齐各自的扁平 JSON → 卷需求 / 对比 / 发布。**EDD 的"调度"本身就是这个父 workflow。**
- 触发时若 worker 上没注册同名 workflow（用例还"待实现"）→ Temporal 报 workflow-type 未注册，**fail loud**，不静默。

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
# eval 项目：一条用例 = 一个 workflow，名字 = case code
@workflow.defn(name="CASE-砍价-预算")           # ← 名字 = 用例 code（绑定约定）
class HaggleBudgetCase:
    @workflow.run
    async def run(self, target) -> dict:
        # driving 系统 + HITL：商家报价靠 signal 喂进来，durable 等（反应式，不是磁带）
        deal = await negotiate(goal="买二手相机", budget=900, merchant=reactive_merchant())
        return {                                # ← 扁平 JSON（骨架 + 自定义 scalar）
            "code": "CASE-砍价-预算",
            "passed": deal.closed and deal.price <= 900,
            "成交价": deal.price,
            "低于预算": deal.price <= 900,
            "砍价轮数": deal.rounds,
        }
```

平台侧只存：`code=CASE-砍价-预算`、说明（+ 可选 trace 链接）、状态=已实现、需求标签。
EDD 按 `code` 触发 → 收这份 JSON → 靠 `code` 对回平台那条用例。**平台不知道、也不需要知道它是哪个文件。**
