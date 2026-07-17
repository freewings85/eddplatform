# 评估的代码/数据边界 · eval entry 模式（定死）

> 本文档锁定 EddPlatform 里"评估到底由谁写、住在哪、平台管什么"这条架构线。
> 结论是在走通 **自定义评估器、每用例参数、trace 导入、HITL 暂停恢复** 几个硬案例后收敛出来的，作为后续实现与原型的准绳。

## 结论（一句话）

评估被切成两半：**声明式的部分是数据、住在平台**；**命令式的部分是代码、住在 git**。
平台**不**引用"一个独立评估项目"，而引用一个 **eval entry** —— 一个 `{ git repo + ref + 运行命令 + 契约 }`。
这个 repo **可以就是被评系统自己的主代码库**（评估代码和主代码写在一起），**也可以是独立评估库**；平台不关心放哪，只认契约。

## 一、评估拆两半

| | 在哪 | 是什么 |
|---|---|---|
| **数据（声明式）** | **平台** | 用例 / Dataset（`inputs` · `expected_output` · `metadata.edd_*` · 需求标签）；**内置评估器 spec**（`ToolCorrectness: {expected_tools:[…]}`、`MaxDuration`… —— 连"每用例要哪个工具"都是数据）；HITL 的外部剧本 / persona 参数 |
| **代码（命令式）** | **git** | **任务适配器**（driving 系统 · 读 output/tool_calls/usage · 发 span · **HITL resume 循环 + 模拟外部方**）；**自定义评估器**（内置盖不住的 `Evaluator` 子类 + 依赖）；**运行入口**；**钉死的依赖（lockfile）** |

关键：**内置评估器不是代码。** 你在用例 YAML 里写 `ToolCorrectness / TrajectoryMatch / MaxDuration`，平台照存照跑，git 里一行都不用为它写。只有内置盖不住的（注入检测、业务判定、外部模拟器）才进 git。

## 二、eval entry 抽象

平台引用的不是"评估项目"，而是：

```
eval entry = { repo, ref(commit/tag), 运行命令, 契约 }
```

- `repo`：主代码库 **或** 独立评估库，皆可。
- `ref`：钉死它 = 评估逻辑 + 依赖 + rubric 一起钉死。
- 运行命令：平台在沙箱里怎么起这次 eval。
- 契约：见第四节。

## 三、两种放法 → 两种用法（不是纯风格）

| | 和主代码同库 · in-process | 独立库 · 前门驱动 |
|---|---|---|
| task 是什么 | 直接 `import` 你的 agent 函数，**没有适配器层** | 打部署好的黑盒（HTTP/SSE），适配器读回执 |
| 评估器档 | ② in-process Python 类（typed `EvaluatorContext` + span 树） | ③ 独立项目 + 镜像 + JSON 契约 |
| 适合 | 同团队 · Python · 可信 | 跨团队 · 非 Python · 黑盒 · 不可信 |
| 天然场景 | **单版本自测 / CI 门禁**（evals-as-tests，跟单测放一起） | **跨版本公平对比**（外环） |

（① 内置评估器永远是数据，和放哪无关。）

## 四、契约（平台 ↔ eval entry）

- 平台 **→** eval entry：注入 **dataset**（用例数据）+ **target**（某系统版本在沙箱里的前门地址 / 或 import 的 ref）+ 运行配置。
- eval entry **→** 平台：每条 case 的结果（**`case_id`** + passed / scores / labels / metrics）。

`case_id` 是接缝：平台管数据、eval entry 管评分，靠它对回去 → 平台做**需求卷积 / 版本对比 / 发布**。

## 五、尺子一致性铁律

评估代码和主代码同库时，**尺子会跟着代码一起演进**：

- **单版本自测**：尺子跟着走反而对（"这个 commit 的 agent 过没过它自己的 evals"）。
- **跨版本对比**：v1、v2 必须用**同一把尺子**。各用各库里的同库 eval → "改善 / 回归"是假结论。所以对比场景必须**把 eval 钉在单一 ref**（或前门驱动两版），不能各评各的。

→ 落回铁律：**尺子必须钉版本**。同库方便，但一进对比，就得把尺子从代码里拎出来钉住。

## 六、三档评估器（和"放哪"正交）

1. **内置**（数据，平台）：`ToolCorrectness` / `TrajectoryMatch` / `ArgumentCorrectness` / `MaxToolCalls` / `MaxDuration` / `HasMatchingSpan`… 声明式 spec，YAML 里 `name + arguments(dict)`，零代码。
2. **in-process Python 类**（同库，可信）：`Evaluator` 子类，实现 `evaluate(ctx)`，拿 typed `EvaluatorContext` + span 树。
3. **独立项目 + 镜像 + JSON 契约**（重 / 非 Python / 不可信）：依赖烤进镜像，评估器在自己容器里跑，走序列化 JSON。

## 七、HITL / deferred 的位置

agent 中途暂停等外部（人审批 / tool 等商家报价）是 pydantic-ai 2.10 的一等机制：
tool 里 `raise CallDeferred`（等外部执行）或 `raise ApprovalRequired`（等人批）→ 本轮 `agent.run` 返回 `DeferredToolRequests(calls, approvals)` → 用 `DeferredToolResults` 通过 `agent.run(message_history=…, deferred_tool_results=…)` resume。

在评估里：

- **任务适配器**（git）负责 resume 循环 + 扮演外部方（商家 persona / 审批策略）。
- **外部剧本 / persona 参数**是 Case 数据（平台，进 `inputs` / `metadata`）。
- 暂停/恢复**对评估器透明** —— 整个多轮 resume 在适配器里跑完，span 树覆盖全过程，`ToolCorrectness` / `TrajectoryMatch` / `MaxToolCalls` 照用。
- HITL 多两把尺子：**该停时停了没**（deferred/approval 会产生带 `pydantic_ai.tool.deferral.name` 的 span → `HasMatchingSpan` 断言）+ **未授权别越权**（收到 `ToolDenied`/未批时没执行危险动作）。
- 长流程可落在 **Temporal**（`pydantic_ai.durable_exec.temporal` 有 `_CallDeferred`/`_ApprovalRequired`）：等 3 天报价的 run 作为 workflow 存活，不占进程 —— 和我们已有的编排层同一个 Temporal。

## 八、版本钉死 = 尺子钉死

钉住 eval entry 一个 ref = 评估逻辑 + 依赖 + rubric 全钉死，比逐个匹配 N 个评估器版本简单。这和钉被评系统模块 tag 是**同一套纪律**（代码进 git、依赖进构建产物、平台只存引用不存代码）。

## repo 形态示例

**同库（in-process，自测）：**
```
你的系统仓库/
  src/agent/...          主代码
  evals/
    run.py               入口：读注入 dataset → evaluate(agent) → 回传 case_id 结果
    evaluators/          自定义评估器（内置的不在这）
    edd.toml             eval entry 契约声明（读取契约、deferred 应答方式）
```

**独立库（前门驱动，对比）：**
```
eval-<系统名>/
  adapter.py             任务适配器：driving 前门 + resume 循环 + 模拟外部方
  evaluators/            自定义评估器
  run.py                 入口：读注入 dataset → evaluate(adapter) → 回传 case_id 结果
  edd.toml               契约：前门 endpoint/协议(sync/sse)、读取契约、deferred 应答
  pyproject.toml         依赖 + lockfile（钉死代码+依赖）
```

两者对平台是**同一个契约**：注入 dataset + target → 回传 `case_id` 结果。
