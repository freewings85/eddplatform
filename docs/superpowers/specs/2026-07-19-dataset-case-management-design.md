# 设计：数据集 · 用例（Case）管理

- 日期：2026-07-19
- 范围：EddPlatform 首个可写功能——数据集内的用例（Case）管理
- 状态：待评审

## 1. 背景与目标

当前平台所有 API 都是**只读**，数据来自内存里的 `sample_data.py`（重启即丢），前端"用例库"页只渲染表格。

本步目标：把「一个数据集里的多条 case」做成可**增删改查 + 导入导出**的真实功能，数据落 **SQLite** 持久化。数据集本身是简单表单壳（一系统一 dataset），**重心在把一条 case 的属性想清楚**，其中最关键的新概念是 case 与**线上轨迹（trace）**的关联。

### 核心产品原则：单一门户，Langfuse 是内嵌引擎

Langfuse 是**集成进本平台的引擎**，不是让用户跳出去的另一个系统。整个平台对用户是一块玻璃（single pane of glass），与 README 里 Backstage 单入口的愿景一致。Langfuse 是否单独部署（现为独立 docker compose）只是部署形态，产品上它属于"我们系统的一部分"。

落到轨迹：**轨迹的存储与查看交给 Langfuse**，平台侧只存指针（trace 引用），将来在平台内**内嵌** Langfuse 的轨迹视图来看——而不是自建 span 树渲染器，也不是甩一个裸外链把用户扔进独立 Langfuse app。

## 2. 范围

### 本步做（In scope）
- `Case` 领域模型补齐属性（含 `trace` 轻引用、`tags`、`description`、时间戳、`author`）。
- SQLite 存储层：只持久化 **cases**；首次为空时用 `sample_data` 播种。
- 后端写接口：case 的 CRUD + 导入 / 导出。
- 前端"用例库"页：工具条（新增 / 导入 / 导出）、行内编辑 / 删除 / 启用开关、用例表单弹窗。

### 本步不做（Out of scope，后续步骤）
- **轨迹管理页 / 内嵌 Langfuse 轨迹视图**：case 页本步只落"链接/引用"，不内嵌 span 树。
- 多数据集（当前一系统一 dataset）。
- 从 Langfuse 反向拉取 trace 内容做快照（本步只存引用，不调 Langfuse 抓数据）。
- dataset 级元信息（name / evaluator_names）的编辑——仍取自静态来源。
- 前端自动化测试设施（vitest 等）；本步前端走手动验证。
- 加权通过率 `weight`、来源 `source`、多轮对话强类型结构。

## 3. Case 数据模型

一条 case 的属性，按"为什么存在"分组。除标注外均为字符串/基础类型。

| 分组 | 属性 | 类型 | 说明 |
|---|---|---|---|
| **身份** | `id` | str | 唯一标识，服务端生成、**稳定不变**——对比时靠它跨系统版本匹配"同一条用例" |
| | `name` | str | 用例名（人读） |
| | `description` | str \| None | 用例意图/在测什么；亦可作 LLM-judge 上下文（新增） |
| **测试内容** | `inputs` | dict \| str | 喂给被评系统入口的输入。单轮=字符串，结构化/多轮=dict |
| | `expected_output` | dict \| str \| None | 参考/黄金答案。**可空**（无参考评估如 rubric judge / span 检查不需要） |
| **分类** | `tags` | list[str] | 标签，数据集内分组/筛选（如 报价/对话/安全/回归）（新增） |
| | `metadata` | dict | 自由扩展键值 |
| **版本 & 适用范围** | `case_version` | str | 用例**自身**的编辑版本（用例被打磨 v1→v2→v3），默认 `v1` |
| | `applicable_versions` | list[str] | 适用的**系统版本**（空=全部通用）。对比只统计两版本都适用的用例 |
| **评估绑定** | `evaluator_names` | list[str] | 这条用例用哪些评估器打分 |
| **轨迹** | `trace` | CaseTrace \| None | 一条 case 对应一条轨迹，轻引用，可空（新增，见下） |
| **生命周期/溯源** | `enabled` | bool | 是否启用，停用的不参与跑，默认 `True` |
| | `created_at` / `updated_at` | datetime \| None | 时间戳，**服务端自动维护**，不进表单（新增） |
| | `author` | str \| None | 创建/负责人，可选（新增） |

### 3.1 CaseTrace（轻引用）

case 对应一条线上真实轨迹。**只存指针，不存轨迹本体**（本体在 Langfuse）。

```python
class CaseTrace(BaseModel):
    ref: str                 # Langfuse trace id
    url: str | None = None   # 直达轨迹视图的链接（host + id 拼；将来指向平台内嵌视图）
    note: str | None = None  # 可选：这条轨迹的问题简述
```

- 录入：填 trace id（或粘 Langfuse URL），可选写一句 `note`。
- 展现（本步）：case 里显示 `note` + 「打开轨迹」链接；**不内嵌 span 树**。
- 未来：`url` 指向平台内的轨迹路由，那里内嵌 Langfuse 视图（另一步）。

## 4. Dataset 模型

保持"一系统一 dataset"（YAGNI，不引入多数据集）。dataset 级元信息（`name`、`evaluator_names`）仍取自静态来源（`sample_data` 或内置默认），**只有 cases 落 SQLite**。`GET /systems/{id}/dataset` 组合：dataset 元信息 + 从 store 读的 cases。存储按 `system_id` 分区，为将来多数据集留出空间（改成按 `dataset_id` 分区即可）。

## 5. 存储层（新增 `src/eddplatform/store/`）

**取舍：Python 标准库 `sqlite3` + 把 Case 存成 JSON 文档**，不引 SQLAlchemy/SQLModel。

- 理由：`Case` 含嵌套/联合字段（`inputs: dict|str`、`applicable_versions: list`、`trace` 对象等），拆成关系列既啰嗦又要加依赖，违背"二次开发要薄"。存 JSON 列让 pydantic `Case` 继续当唯一事实源，最薄；`sqlite3` 是标准库，**零新依赖**。
- 表结构：
  ```sql
  CREATE TABLE IF NOT EXISTS cases (
    system_id TEXT NOT NULL,
    case_id   TEXT NOT NULL,
    position  INTEGER NOT NULL,   -- 保序
    data      TEXT NOT NULL,      -- Case 的 JSON
    PRIMARY KEY (system_id, case_id)
  );
  ```
- DB 路径：默认 `./data/eddplatform.db`，可用环境变量 `EDDPLATFORM_DB` 覆盖；`data/` 加进 `.gitignore`。
- **播种**：初始化时若某 system 无 cases，用 `sample_data.DATASET`（及其它系统的默认）灌入，保证 UI 不空。
- `CaseStore` 接口（连接每次操作即开即用或单例，线程安全用 `check_same_thread=False` + 简单锁）：
  - `list_cases(system_id) -> list[Case]`（按 position 排序）
  - `get_case(system_id, case_id) -> Case | None`
  - `add_case(system_id, case) -> Case`（`id` 缺失则生成=现有数字 id 最大值+1；`position` 取末尾；写 `created_at/updated_at`）
  - `update_case(system_id, case_id, case) -> Case`（保持 `id/created_at/position`，刷新 `updated_at`）
  - `delete_case(system_id, case_id) -> None`
  - `import_cases(system_id, cases, mode) -> ImportResult`（`mode="append"` 按 id upsert；`mode="replace"` 清空重建）
  - `export_cases(system_id) -> list[Case]`

## 6. API 层（`api/app.py` 增写接口）

vite dev 已把 `/api` 代理到 :8000，无需 CORS。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/systems/{id}/dataset` | 现有，改为 cases 从 store 读 |
| POST | `/systems/{id}/cases` | 新增 case（body=Case，`id` 可省由服务端生成）→ 返回创建的 Case |
| PUT | `/systems/{id}/cases/{case_id}` | 编辑 → 返回更新后的 Case |
| DELETE | `/systems/{id}/cases/{case_id}` | 删除 |
| GET | `/systems/{id}/cases/export` | 导出 `list[Case]` JSON（前端触发下载） |
| POST | `/systems/{id}/cases/import` | 导入，body `{cases: [...], mode: "append"\|"replace"}`，默认 `append`；返回 `{added, updated, total}` |

- 校验：请求体走 pydantic `Case`（部分字段可选）。`case_id` 不存在时 PUT/DELETE 返回 404。
- 导入 `mode` 默认 `append`（按 id upsert，保留其它）；`replace` 清空重建。

## 7. 前端（`web/src/`）

- **拆分**：把 `Datasets` 从 `App.tsx` 抽到独立文件 `Datasets.tsx`，用例表单弹窗 `CaseForm.tsx`，保持文件聚焦。
- `types.ts`：`Case` 补齐 `inputs / expected_output / metadata / description / tags / trace / author / created_at / updated_at`；新增 `CaseTrace` 类型。
- `api.ts`：加 `createCase / updateCase / deleteCase / exportCases / importCases`。
- **UI**：
  - 表格上方工具条：**新增用例 · 导入 · 导出**。
  - **标签筛选条**：列出数据集内全部标签为可点 chip，点选按标签过滤用例；多选=且（case 需含全部所选标签），可一键清除；计数显示"过滤数 / 总数"。
  - 表格列在现有基础上加 `tags`、`trace`（有则显示「轨迹」链接图标）、动作列（**编辑 / 删除**）、**启用开关**。
  - 表单弹窗字段：名称、描述、inputs（JSON 文本域）、expected_output（JSON 文本域，可空）、tags（多标签输入）、用例版本、适用系统版本（多选/逗号）、评估器（从该系统可用评估器多选）、trace（trace id/URL + note）、metadata（JSON 可空）、启用。
  - 提交前对 inputs / expected_output / metadata 做 JSON 校验（也允许纯字符串输入）。
  - 导入：粘贴/上传 JSON 数组 + 选 mode（append/replace）。导出：下载当前 cases JSON。

## 8. 测试

- 后端 pytest（新增 `tests/test_case_store.py`、`tests/test_case_api.py`）：
  - `CaseStore` CRUD、id 生成、保序、import 两种 mode、export、播种（用临时 db 文件，`EDDPLATFORM_DB` 指向 tmp）。
  - FastAPI `TestClient` 覆盖新接口的正常路径 + 404 + 导入导出。
- 前端：本步无自动化测试，手动验证（新增/编辑/删除/启用切换/导入导出走通）。

## 9. 已定决策

- 持久化：**SQLite（标准库 sqlite3 + JSON 文档列）**。
- 操作范围：**CRUD + 导入/导出**。
- 一条 case **一条**轨迹；轨迹**轻引用**（ref/url/note），存储与查看交给 Langfuse。
- Langfuse 作为**内嵌引擎**，产品上属于本平台；轨迹内嵌视图为**后续步骤**。
- 数据集：一系统一 dataset，dataset 元信息静态，仅 cases 持久化。
- 导入默认 `append`（按 id upsert），`replace` 清空重建。
