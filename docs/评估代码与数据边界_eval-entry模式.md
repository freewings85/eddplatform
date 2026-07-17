# 评估架构（定死）：EDD 只做管理与调度，逻辑全在 pydantic-evals 代码

> 本文档锁定 EddPlatform 里"评估到底由谁写、住在哪、平台管什么"这条架构线。
> 结论是在走通 **自定义评估器、每用例参数、trace 导入、HITL 暂停恢复** 几个硬案例、并做了大幅化简后收敛出来的，作为后续实现与原型的准绳。

## 结论（一句话）

**EDD 平台 = 用例的管理 + 调度；用例的真逻辑 = git 里标准的 pydantic-evals 代码。**
平台给每条用例挂"编号 + 说明 + 代码文件路径"，负责"跑哪些用例 × 哪个系统版本 × 哪个沙箱、把结果收回来"做需求卷积 / 版本对比 / 发布。
**平台不理解、不校验用例逻辑 —— 即使说明和代码不一致，平台也感知不到。这是故意的。**

## 一、用例（平台侧的登记项）

一个用例 = ：

| 组成 | 说明 |
|---|---|
| `code` | 唯一编号，平台内主键，也是结果对回来的接缝 |
| **说明** | ① yaml 式结构描述（inputs / 期望 / 元数据，可选）+ ② 一段纯文字描述；可选**关联一条 trace** |
| **代码文件路径** | git 项目 + 具体代码文件，指向这条用例的实现 |
| **状态** | 待实现 / 已实现（是否已回填代码路径） |

平台还挂**管理元数据**（驱动外环，是平台的真价值）：需求标签（→ 需求达标卷积）、适用系统版本（→ 跨版本对比公平性）、Dataset 分组、启用 / 归档。

**生命周期**：新建时只填 `code` + 说明（可带 trace，可不带）→ 开发者打开平台看到这条用例、在 git 里实现它、把代码路径回填 → 用例才算完整。
平台里的用例**退化成纯描述 + 管理**；真逻辑全在代码。

## 二、执行 = 一个个跑用例文件

真正执行 = 逐个跑用例的代码文件，**用例逻辑就是标准的 pydantic-evals 代码**：inputs、HITL 模拟、评估器、判定，全在代码文件里。
EDD 只负责**调度**（哪些 case × 哪个版本 × 哪个沙箱）+ **采集结果**。它不进代码、不懂逻辑。

## 三、平台不做对齐（故意）

平台**不校验**说明 ↔ 代码是否一致。代码是唯一真相，说明只是给人看 / 给管理用的元数据，两者漂移**不可见、可接受**。
→ 这一刀砍掉了一整摊复杂度：评估器当数据存（EvaluatorDef / params）、内置 vs 自定义分档、schema 发布 + 双向校验、"平台引用一把没写的尺子再等开发回填"的来回 handoff —— **全部不需要了**。平台不再假装懂评估。

## 四、输出 JSON 规范（平台 ↔ 代码唯一硬接口）

每条用例跑完，回吐一个**扁平**的 JSON。这是平台能做管理 / 对比 / 卷需求的**全部依据**。

**骨架（固定两个字段）：**

```json
{ "code": "CASE-砍价-预算", "passed": false, "...": "用例自定义的扁平字段" }
```

- `code` —— 哪条用例，平台靠它对回去。
- `passed` —— 总判定（bool），平台卷"需求达标"**只认它**。

**其余字段用例自己定，但强制一层（scalar）：**

```json
{
  "code": "CASE-砍价-预算",
  "passed": false,
  "成交价": 1000,
  "低于预算": false,
  "砍价轮数": 3,
  "结果": "超预算成交"
}
```

- **按类型自动定角色**（和 pydantic-evals 一致）：`bool → 判定 / 数值 → 分数 / 字符串 → 标签`。平台照类型画列、跨版本比、聚合，**不用懂字段语义**。
- **禁止嵌套、禁止对象数组**。要表达"每轮报价"就压成标量 `砍价轮数: 3`，别塞 list。
- 与 pydantic-evals 结果天然对应：evaluator 的 `assertions(bool)` / `scores(数值)` / `labels(字符串)` 摊平即是这些字段；`passed` = 所有 assertion 为真。

**好处**：同一条 case 的 v1 / v2 字段一致 → 直接可比；`passed` + 需求标签 → 卷达标；每个 scalar 就是一列，平台零理解成本。

## 五、尺子一致性 = 钉 ref

跨版本对比要求两版用**同一把尺子**。做法：一次 Comparison 里，v1、v2 跑**同一个 eval 项目 ref**。钉一个 ref = 评估逻辑 + 依赖 + rubric 全钉死。
（单版本自测则无所谓，尺子跟着代码走反而对。）

## 六、HITL / deferred（在用例代码里，平台无感）

agent 中途暂停等外部（人审批 / tool 等商家报价）是 pydantic-ai 一等机制：tool 里 `raise CallDeferred` / `ApprovalRequired` → `agent.run` 返回 `DeferredToolRequests` → 用 `DeferredToolResults` resume。

这些**全在用例的代码文件里**：

- 任务适配器负责 resume 循环 + **反应式**模拟外部方（商家会对新还价做反应，**不是放固定磁带**）。
- 暂停 / 恢复对评估透明 —— span 树覆盖整个多轮过程，`ToolCorrectness` / `TrajectoryMatch` 照用。
- 长流程可落 Temporal（`pydantic_ai.durable_exec.temporal` 有 `_CallDeferred` / `_ApprovalRequired`），等 3 天报价的 run 作为 workflow 存活。
- 平台对这一切**无感**，只在最后收那份扁平 JSON。

## 七、评估器概念在平台侧退化

因为逻辑全在代码，平台**不建评估器模型**（无 EvaluatorDef、无参数存储、无内置/自定义分档）。
评估器只是用例代码里用到的东西 —— 现成的 pydantic-evals 内置（`EqualsExpected` / `ToolCorrectness` / `TrajectoryMatch` / `LLMJudge` / `GEval`…），或自己写的 `Evaluator` 子类。**平台一律不感知，只收扁平 JSON。**

## 用例文件形态示例

```python
# cases/砍价_预算.py  ——  这条用例的全部逻辑（标准 pydantic-evals）
from pydantic_evals import Case, Dataset

def build_merchant(policy):     # 反应式商家：对 agent 的还价做反应，不是磁带
    ...

async def run():
    # 1) driving 系统 + resume 循环（喂反应式商家的报价）
    deal = await negotiate(goal="买二手相机", budget=900, merchant=build_merchant(...))
    # 2) 判定 + 摊平成扁平 JSON（骨架 code/passed + 自定义 scalar）
    return {
        "code": "CASE-砍价-预算",
        "passed": deal.closed and deal.price <= 900,
        "成交价": deal.price,
        "低于预算": deal.price <= 900,
        "砍价轮数": deal.rounds,
    }
```

平台侧只存：`code=CASE-砍价-预算`、说明（+ 可选 trace 链接）、代码路径 `myrepo/cases/砍价_预算.py`、需求标签、状态=已实现。**跑完收那份扁平 JSON，靠 `code` 对回去。**
