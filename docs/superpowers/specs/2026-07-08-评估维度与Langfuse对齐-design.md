# 设计：评估维度体系 × 与 Langfuse 对齐

- 日期：2026-07-08
- 状态：设计定稿（原型「Langfuse 评估标准指南」子页已实现），待写实现计划
- 相关：`prototype/index.html`（评估器页 + eval-guide 子页）、`src/eddplatform/evals/`
- 前置阅读：`2026-07-08-需求管理追溯-design.md`（同批设计）

## 背景

现有评估内核只能表达少数维度。发布把关实际要评的维度更多：**结果正确性、输出文字质量、轨迹质量（最小调用链路）、速度/延迟、TTFT（首 token 时延）、成本**。本 spec 把这套维度体系化，并明确每个维度**在 Langfuse 里怎么落**（引擎复用 Langfuse，不自研），以及本地内核要补哪些代码。

## Langfuse 能力核实（2026-07 官方文档）

Langfuse 把"评估"分两层：

1. **评估器 → Score**（定义标准处）：
   - **LLM-as-a-Judge**：写 rubric，`{{变量}}` 映射 trace 字段，输出 Numeric/Categorical/Boolean；可跑在 experiment / trace / **单个 observation** 上。
   - **Code evaluator**：Python `evaluate()` 确定性校验，读 input/output/metadata/expected，2s 内跑完；适合 exact match、JSON schema、**工具调用/自定义规则**。
   - **SDK 自定义 Score**：`create_score(...)` 任意回灌，4 种数据类型（Numeric/Categorical/Boolean/Text）。
2. **可观测指标**（自动采集，非 Score）：**延迟 / 成本 / token / TTFT**（TTFT 需 emit `completion_start_time`）挂在 trace/observation 上，经 Metrics API / Latency & Cost Dashboard 看聚合。要做成"通过/不通过门禁"，用 SDK 自定义 Score 回灌一条 Boolean。

**口径**：**质量类维度**（正确性/文字/轨迹）= Langfuse 评估器→Score；**信号类维度**（延迟/TTFT/成本）= Langfuse 可观测指标，自动采、看 dashboard，要卡发布就回灌一条 Boolean Score。

（官方链接见原型 eval-guide 子页，已内嵌核实过的 URL。）

## 维度 → 落法 → 本地内核缺口

| 维度 | 类别 | Langfuse 落法 | 本地内核现状/缺口 |
|---|---|---|---|
| 结果正确性 | 质量 | Code evaluator（exact/JSON schema） | ✅ `EqualsExpected`/`Contains` 已有 |
| 输出文字质量 | 质量 | LLM-as-a-Judge（rubric） | ✅ `LLMJudge` 已有（需接 judge client） |
| 轨迹质量/最小链路 | 质量 | Code evaluator over observations | ⚠️ 仅 `SpanPresent`（存在性）；**缺结构评估器** |
| 速度/延迟（总/P95） | 信号 | 自动采；门禁→SDK Score | ✅ 总耗时 `MaxDuration` 有；P95 靠 Langfuse |
| TTFT | 信号 | emit `completion_start_time`；门禁→SDK Score | ❌ **EvalContext 无字段；target 不流式** |
| 成本/用例 | 信号 | usage 自动算；门禁→SDK Score | ❌ **EvalContext 无 usage 字段** |

## 本地内核改动（`src/eddplatform/evals/`）

用户确认本轮 **spec + 改代码**。改动保持"薄 + 中立接口"，不与 Langfuse 争职责。

### 1. 扩 `EvalContext`（`engine.py`）

补上信号类原料 + 轨迹结构：

```python
@dataclass
class EvalContext:
    inputs: Any
    output: Any
    expected_output: Any = None
    metadata: dict = field(default_factory=dict)
    duration_s: float = 0.0
    spans: list[dict] = field(default_factory=list)      # 已有：OTel 轨迹
    attributes: dict = field(default_factory=dict)        # 已有
    # 新增（来自 trace / target；本地兜底可空）：
    ttft_s: float | None = None                           # 首 token 时延
    usage: dict = field(default_factory=dict)             # {input, output, total} tokens
    cost: float | None = None                             # 花费（币值）
```

### 2. 新增轨迹结构评估器（`engine.py`）

读 `spans` 的**结构**而非仅存在性：

```python
@dataclass
class MinimalToolChain:   # 工具调用数 ≤ max、无重复、（可选）顺序符合
    name: str
    max_calls: int = 2
    no_duplicate: bool = True
    tool_span_marker: str = "tool"   # 判定哪些 span 是工具调用

@dataclass
class MaxTTFT:            # ttft_s ≤ seconds（信号类门禁的本地版）
    name: str
    seconds: float

@dataclass
class MaxCost:           # cost ≤ budget
    name: str
    budget: float
```

`MaxDuration` 保留。这些评估器输出 assertion（bool），与现有归类一致。

### 3. `EvaluatorDef` 扩字段（`domain/models.py`）

- `ContextField` 枚举补：`TTFT`、`USAGE`、`COST`。
- `EvaluatorKind` 视需要补 `TRAJECTORY`（或继续用 `BUILTIN` + `builtin_type` 承载 `MinimalToolChain` 等）。首选后者，少动枚举。
- `build_evaluator()` 增加对新 `builtin_type`（`MinimalToolChain`/`MaxTTFT`/`MaxCost`）的装配。

### 4. 维度分类（元数据）

`EvaluatorDef` 加 `dimension: str | None`（取值：正确性/文字质量/轨迹/延迟/TTFT/成本），仅用于 UI 分组与报告分区。不影响执行。

### 5. Target 支持 TTFT（`targets.py`）

`HttpTarget` 现为阻塞 `httpx.request`，测不了 TTFT。新增可选流式路径：

```python
@dataclass
class HttpTarget:
    ...
    stream: bool = False        # True 时用 httpx.stream，记录首字节/首 token 时间
    # 返回 (output, meta) 其中 meta 含 ttft_s；或把 meta 塞进 EvalContext
```

**边界**：TTFT 的**首选来源仍是被评系统 emit `completion_start_time` 到 trace**（Langfuse 口径）；harness 流式掐表是**兜底**（被评系统未 emit 时）。二者择一，spec 默认优先读 trace。

### 6. Langfuse 适配器富化（`evals/adapters/langfuse.py`）

- `run_version` 的 evaluator 除质量类打分外，**信号类门禁**用 `create_score` 回灌 Boolean（延迟/TTFT/成本达标），随 dataset run 进 Compare。
- 从 trace/observation 读回 latency/usage/ttft 填进传给评估器的 ctx（生产路径）。

## 原型（已完成，作为本 spec 的 UI 基准）

- 评估器页 → 「📖 Langfuse 评估标准指南」子页：两层模型、维度→落法对照表（标注 ✅原生/⚠️需自写/⚠️需先 emit）、三段示例（LLM-judge rubric / Code evaluator 轨迹 / SDK create_score 门禁）、核实过的官方文档链接、跳转按钮。
- 评估器定义表单未来需把「读取(ctx)」下拉补上 `ttft / usage / cost / span_tree(结构)`，与本 spec 的 `ContextField` 扩展一致。

## 测试

- `tests/test_engine.py`：`MinimalToolChain`（步数/去重）、`MaxTTFT`、`MaxCost`；扩展后的 `EvalContext` 默认值。
- `EvaluatorDef` 新 `builtin_type` 的 `build_evaluator` 装配。
- `HttpTarget(stream=True)` 的 ttft 记录（用本地假服务器 / mock）。

## 不在本范围（未来）

- 维度**加权总分 / 门禁策略引擎**（现在各维度独立 assertion，全过才过）。
- 评估器定义表单的可视化编辑（原型已画，前端实现归 T1-3/T1-2 前端部分）。
- 生产从 Langfuse 批量回读指标做二次分析。

## 验收标准

1. `EvalContext` 含 `ttft_s/usage/cost`；新评估器（MinimalToolChain/MaxTTFT/MaxCost）单测通过。
2. `EvaluatorDef` 能表达轨迹/TTFT/成本维度并被 `build_evaluator` 正确装配。
3. `HttpTarget(stream=True)` 能测得 TTFT（或明确走 trace 读取路径）。
4. Langfuse 适配器把信号类门禁作为 Boolean Score 回灌，随 dataset run 可在 Compare 看。
5. `pytest` 全绿；原型 eval-guide 与 spec 口径一致。
