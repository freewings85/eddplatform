# 用例评估管理系统真运行（M1+M2 平台侧）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 平台从"样例数据+内存"改造为"MySQL 持久化 + 界面可注册系统/评估程序/任务 + 一键执行经 Temporal 逐用例评估 + 真运行记录"，交付零假数据空态。

**Architecture:** 存储层统一为 `store/db.py`（PyMySQL，JSON 文档列模式）；API 层删除 `sample_data` 全部依赖，System/EvalProgram/Task/Run 各配 store + CRUD；执行 = `POST /run` 异步 start `RunTaskWorkflow` + 后台协程回写；workflow 在环境就绪后按评估程序 `code` 逐 case `execute_child_workflow`（方案 A：平台=client，评估程序仓=worker）。

**Tech Stack:** Python 3.11 / FastAPI / pydantic v2 / PyMySQL / temporalio；React18+TS+Vite；pytest；Playwright(python) 自验。

## Global Constraints

- MySQL 5.7.44 @ `127.0.0.1:3306`，`root/root`；业务库 `eddplatform`，测试库 `eddplatform_test`（均由代码自动 CREATE DATABASE IF NOT EXISTS，utf8mb4）。
- 环境变量：`EDD_MYSQL_HOST/PORT/USER/PASSWORD/DB`（默认如上）。
- **零假数据**：`src/eddplatform/api/sample_data.py` 最终删除；不留任何 seed；前端所有列表有空态文案。
- SQLite 全面移除（`sqlite3` import、`EDDPLATFORM_DB`、`data/` 目录逻辑全删）。
- 命令：Python 测试 `.venv/bin/pytest tests/ -x -q`；前端构建 `cd web && npm run build`（tsc 必须过）。
- 提交信息中文 conventional style，尾行 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
- pymysql 已在 pyproject（uv 已装）。占位符用 `%s`；连接 `charset="utf8mb4"`、`cursorclass=DictCursor`。

---

### Task 1: MySQL 连接工厂 `store/db.py`

**Files:**
- Create: `src/eddplatform/store/db.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `Db(database: str | None = None)`；`Db.connect() -> pymysql.Connection`；`Db.truncate_all()`（测试用）。所有表 schema 集中在 `db.py` 的 `SCHEMA` 列表。

- [ ] **Step 1: 写 failing test**

```python
# tests/test_db.py
"""Db：建库建表 + 连接可用。打真 MySQL（eddplatform_test 库）。"""
import pymysql
import pytest

from eddplatform.store.db import Db


def test_db_creates_database_and_tables(test_db: Db):
    conn = test_db.connect()
    try:
        with conn.cursor() as c:
            c.execute("SHOW TABLES")
            tables = {list(r.values())[0] for r in c.fetchall()}
    finally:
        conn.close()
    assert {"cases", "tags", "systems", "eval_programs", "tasks", "runs", "case_results"} <= tables


def test_truncate_all_clears_rows(test_db: Db):
    conn = test_db.connect()
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO systems(system_id, data) VALUES(%s, %s)", ("s1", "{}"))
        conn.commit()
    finally:
        conn.close()
    test_db.truncate_all()
    conn = test_db.connect()
    try:
        with conn.cursor() as c:
            c.execute("SELECT COUNT(*) AS n FROM systems")
            assert c.fetchone()["n"] == 0
    finally:
        conn.close()
```

```python
# tests/conftest.py
"""测试公共夹具：真 MySQL 测试库（eddplatform_test），每测清表。

MySQL 不可达时 skip 整个依赖它的测试（本项目约定本机必有 MySQL，skip 仅为容错）。
"""
import os

import pytest

os.environ.setdefault("EDD_MYSQL_DB", "eddplatform_test")

from eddplatform.store.db import Db  # noqa: E402


def _mysql_available() -> bool:
    import socket
    try:
        s = socket.create_connection(
            (os.environ.get("EDD_MYSQL_HOST", "127.0.0.1"),
             int(os.environ.get("EDD_MYSQL_PORT", "3306"))), timeout=2)
        s.close()
        return True
    except OSError:
        return False


@pytest.fixture()
def test_db() -> Db:
    if not _mysql_available():
        pytest.skip("MySQL 不可达（127.0.0.1:3306）")
    db = Db(database="eddplatform_test")
    db.truncate_all()
    return db
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: FAIL（`ModuleNotFoundError: eddplatform.store.db`）

- [ ] **Step 3: 实现 `store/db.py`**

```python
# src/eddplatform/store/db.py
"""MySQL 连接工厂 + 全部表 schema。

- JSON 文档列模式：领域对象整体存 ``data JSON``，检索键单独成列。
- 库不存在自动创建（utf8mb4）；表 ``CREATE TABLE IF NOT EXISTS``。
- 配置走环境变量 ``EDD_MYSQL_HOST/PORT/USER/PASSWORD/DB``。
"""

from __future__ import annotations

import os

import pymysql
from pymysql.cursors import DictCursor

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS cases (
        system_id VARCHAR(64) NOT NULL,
        case_id   VARCHAR(64) NOT NULL,
        position  INT NOT NULL,
        data      JSON NOT NULL,
        PRIMARY KEY (system_id, case_id)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS tags (
        system_id VARCHAR(64) NOT NULL,
        id        VARCHAR(64) NOT NULL,
        name      VARCHAR(255) NOT NULL,
        parent_id VARCHAR(64) NULL,
        position  INT NOT NULL,
        PRIMARY KEY (system_id, id)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS systems (
        system_id VARCHAR(64) NOT NULL,
        data      JSON NOT NULL,
        PRIMARY KEY (system_id)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS eval_programs (
        system_id  VARCHAR(64) NOT NULL,
        program_id VARCHAR(64) NOT NULL,
        data       JSON NOT NULL,
        PRIMARY KEY (system_id, program_id)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS tasks (
        system_id VARCHAR(64) NOT NULL,
        task_id   VARCHAR(64) NOT NULL,
        data      JSON NOT NULL,
        PRIMARY KEY (system_id, task_id)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS runs (
        run_id     VARCHAR(64) NOT NULL,
        system_id  VARCHAR(64) NOT NULL,
        task_id    VARCHAR(64) NOT NULL,
        status     VARCHAR(16) NOT NULL,
        created_at DATETIME NOT NULL,
        data       JSON NOT NULL,
        PRIMARY KEY (run_id)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS case_results (
        run_id  VARCHAR(64) NOT NULL,
        case_id VARCHAR(64) NOT NULL,
        data    JSON NOT NULL,
        PRIMARY KEY (run_id, case_id)
    ) CHARACTER SET utf8mb4""",
]

TABLES = ["cases", "tags", "systems", "eval_programs", "tasks", "runs", "case_results"]


class Db:
    def __init__(self, database: str | None = None) -> None:
        self.host = os.environ.get("EDD_MYSQL_HOST", "127.0.0.1")
        self.port = int(os.environ.get("EDD_MYSQL_PORT", "3306"))
        self.user = os.environ.get("EDD_MYSQL_USER", "root")
        self.password = os.environ.get("EDD_MYSQL_PASSWORD", "root")
        self.database = database or os.environ.get("EDD_MYSQL_DB", "eddplatform")
        self._ensure()

    def _server_conn(self) -> pymysql.connections.Connection:
        return pymysql.connect(host=self.host, port=self.port, user=self.user,
                               password=self.password, charset="utf8mb4",
                               cursorclass=DictCursor, autocommit=True)

    def connect(self) -> pymysql.connections.Connection:
        return pymysql.connect(host=self.host, port=self.port, user=self.user,
                               password=self.password, database=self.database,
                               charset="utf8mb4", cursorclass=DictCursor)

    def _ensure(self) -> None:
        conn = self._server_conn()
        try:
            with conn.cursor() as c:
                c.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self.database}` CHARACTER SET utf8mb4"
                )
        finally:
            conn.close()
        conn = self.connect()
        try:
            with conn.cursor() as c:
                for ddl in SCHEMA:
                    c.execute(ddl)
            conn.commit()
        finally:
            conn.close()

    def truncate_all(self) -> None:
        conn = self.connect()
        try:
            with conn.cursor() as c:
                for t in TABLES:
                    c.execute(f"TRUNCATE TABLE `{t}`")
            conn.commit()
        finally:
            conn.close()
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_db.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/eddplatform/store/db.py tests/test_db.py tests/conftest.py
git commit -m "feat(store): MySQL 连接工厂 Db + 全量表 schema（JSON 文档列，自动建库建表）"
```

---

### Task 2: `CaseStore` 迁移 MySQL

**Files:**
- Modify: `src/eddplatform/store/case_store.py`（整体重写连接层，方法签名不变）
- Modify: `src/eddplatform/store/__init__.py`
- Modify: `tests/test_case_store.py`（夹具改用 `test_db`）
- Modify: `tests/test_case_api.py`（同）

**Interfaces:**
- Consumes: `Db`（Task 1）。
- Produces: `CaseStore(db: Db | None = None)`，其余公有方法签名不变（`list_cases/get_case/add_case/update_case/delete_case/export_cases/import_cases/rewrite_tag_prefix`）。**删除 `seed_if_empty`**。

- [ ] **Step 1: 改测试夹具**

`tests/test_case_store.py` 里所有 `CaseStore(db_path=...)` / tmp_path 用法改为：

```python
import pytest
from eddplatform.store import CaseStore

@pytest.fixture()
def store(test_db):
    return CaseStore(db=test_db)
```

删除 `seed_if_empty` 相关测试用例。`tests/test_case_api.py` 中若直接构造 store 同样处理（API 层夹具在 Task 8 统一改，本步先只让 store 层测试指向 MySQL）。

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_case_store.py -v`
Expected: FAIL（`TypeError: unexpected keyword argument 'db'`）

- [ ] **Step 3: 重写 `case_store.py` 连接层**

保持文件结构与方法体逻辑，替换：

```python
# 头部
from eddplatform.domain.models import Case
from eddplatform.store.db import Db

class CaseStore:
    def __init__(self, db: Db | None = None) -> None:
        self.db = db or Db()
        self._lock = threading.Lock()

    def _connect(self):
        return self.db.connect()
```

全部 SQL 的 `?` → `%s`；`conn.execute(...)` → `with conn.cursor() as c: c.execute(...)`（pymysql 连接对象没有 execute）。行访问 `r["data"]` 不变（DictCursor）。删除 `sqlite3`/`os.environ["EDDPLATFORM_DB"]`/`Path.mkdir`/`DEFAULT_DB`/`seed_if_empty`。示例（`list_cases`，其余方法同样模式改写）：

```python
    def list_cases(self, system_id: str) -> list[Case]:
        conn = self._connect()
        try:
            with conn.cursor() as c:
                c.execute(
                    "SELECT data FROM cases WHERE system_id=%s ORDER BY position",
                    (system_id,),
                )
                rows = c.fetchall()
        finally:
            conn.close()
        return [Case.model_validate_json(r["data"]) for r in rows]
```

注意 `import_cases` 里的 `SELECT COUNT(*) AS n` 与 `_next_position` 的 `MAX(position) AS m` 语法 MySQL 通用，仅换占位符。

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_case_store.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add src/eddplatform/store/case_store.py src/eddplatform/store/__init__.py tests/test_case_store.py tests/test_case_api.py
git commit -m "refactor(store): CaseStore sqlite→MySQL（签名不变，删 seed_if_empty）"
```

---

### Task 3: `TagStore` 迁移 MySQL

**Files:**
- Modify: `src/eddplatform/store/tag_store.py`
- Modify: `tests/test_tag_store.py`、`tests/test_tag_api.py`

**Interfaces:**
- Produces: `TagStore(db: Db | None = None)`；`list_tags/paths/add_tag/rename_tag/delete_tag` 签名不变；**删除 `seed_if_empty`**。

- [ ] **Step 1: 测试夹具改 `TagStore(db=test_db)`**（同 Task 2 模式；删 seed 相关测试）
- [ ] **Step 2: 跑 `tests/test_tag_store.py` 确认失败**
- [ ] **Step 3: 同 Task 2 模式重写连接层**（`?`→`%s`、cursor 模式、删 sqlite/seed；`parent_id` 为 NULL 判断用 `IS NULL` 的地方检查 SQL 兼容）
- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_tag_store.py tests/test_case_store.py -v`

- [ ] **Step 5: Commit**

```bash
git add src/eddplatform/store/tag_store.py tests/test_tag_store.py tests/test_tag_api.py
git commit -m "refactor(store): TagStore sqlite→MySQL（签名不变，删 seed_if_empty）"
```

---

### Task 4: 领域模型调整（System/EvalProgram/Task/RunRecord）

**Files:**
- Modify: `src/eddplatform/domain/models.py`
- Test: `tests/test_models.py`（追加）

**Interfaces:**
- Produces（后续任务全部依赖这些确切字段）:
  - `System`：加 `description: str | None = None`；`modules` 保持可空列表。
  - `EvalProgram`：加 `code: str`（RunCase workflow 名 = task queue）、`ref: str = "main"`；`image/dockerfile` 改 `str | None = None`（约定式部署不需要）；`branch` 删除（被 `ref` 取代）；`versions/prod_tag` 删除。
  - `Task`：加 `eval_program_id: str | None = None`。
  - `RunRecord` 整体重定义（旧字段服务于假数据，删）：

```python
class RunStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RunRecord(BaseModel):
    """一次 task 执行（experiment）：Temporal workflow 的平台侧记录。"""

    id: str = ""
    system_id: str
    task_id: str
    task_name: str = ""
    status: RunStatus = RunStatus.RUNNING
    workflow_id: str = ""
    namespace: str = ""
    versions: dict[str, str] = {}          # {system: sha, eval: sha}
    outcomes: list[dict] = []              # 每条前置条件的 OutcomeOut dict
    detail: str = ""                       # 失败原因等
    created_at: datetime | None = None
    finished_at: datetime | None = None
```

  - 删除模型：`Evaluation`、`EvalResult`、`Comparison`、`MetricDelta`、`Environment`、`SandboxConfig`、`SystemVersion`、`EvaluatorDef`、`EvaluatorKind/OutputType/ContextField/EvaluatorScope/EvalStatus/RunType/IsolationLevel/VersionStatus` 枚举（全部只被假数据用）。`CaseResult` 保留并改造：

```python
class CaseResult(BaseModel):
    """单用例评估结果（由评估程序 worker 经 RunCase workflow 返回）。"""

    case_id: str
    status: str = "passed"                 # passed | failed | error
    scores: dict[str, float] = {}
    metrics: dict[str, float] = {}
    detail: str = ""
    trace_url: str | None = None
```

- [ ] **Step 1: 写 failing test**

```python
# tests/test_models.py 追加
def test_eval_program_has_code_and_ref():
    from eddplatform.domain.models import EvalProgram
    ep = EvalProgram(id="ep1", system_id="s", name="评估程序", git_url="/repo", code="chatagent-eval")
    assert ep.ref == "main" and ep.code == "chatagent-eval"


def test_run_record_shape():
    from eddplatform.domain.models import RunRecord, RunStatus
    r = RunRecord(system_id="s", task_id="t")
    assert r.status == RunStatus.RUNNING and r.outcomes == []
```

- [ ] **Step 2: 跑 `tests/test_models.py` 确认失败**
- [ ] **Step 3: 按上述接口改 `models.py`**（删除的模型若被 `sample_data.py` 引用——本任务同时把 `api/sample_data.py` **整个删除**，`app.py` 里 `import sample_data as sd` 及所有 `sd.` 引用临时删除/置空：`list_systems` 等先返回 `[]`，Task 5-8 再接真 store；`/api/versions`、`/api/evaluators`、`/api/sandbox-configs`、`/api/environments`、`/api/evaluations`、`/api/comparison` 端点**直接删除**）
- [ ] **Step 4: 全量跑**

Run: `.venv/bin/pytest tests/ -x -q`
Expected: `tests/test_api.py` 等引用已删模型/端点的测试会失败——**同步修剪**：删掉 test_api.py 中 versions/evaluators/sandbox/environments/evaluations/comparison 相关断言与假数据断言（保留 health、cases、tags 测试，system 列表断言改为空 `[]`）。`tests/sample_fixtures.py`/`tests/release_sample.py` 若引用已删模型，改为本地最小构造或删除对应 fixture。跑到全绿。

- [ ] **Step 5: Commit**

```bash
git add -A src/eddplatform tests
git commit -m "refactor(domain,api): 模型收敛真运行所需（EvalProgram+code/ref、RunRecord 重定义）+ 删 sample_data 与假数据端点"
```

---

### Task 5: SystemStore + 系统 CRUD API

**Files:**
- Create: `src/eddplatform/store/system_store.py`
- Modify: `src/eddplatform/store/__init__.py`、`src/eddplatform/api/app.py`
- Test: `tests/test_system_api.py`

**Interfaces:**
- Produces: `SystemStore(db)`：`list() -> list[System]`、`get(system_id) -> System | None`、`create(System) -> System`（重复 id 抛 `ValueError`）、`update(system_id, System) -> System`（无则 `KeyError`）、`delete(system_id)`（无则 `KeyError`）。
- API：`GET /api/systems`、`GET/POST/PUT/DELETE /api/systems/{id}`；POST 重复→409；PUT/DELETE 缺失→404；DELETE 在该系统还有 task 或 run 时→409（`task_store/run_store` 在 Task 6/7 之后接入该校验，本任务先留 store 判断位）。

- [ ] **Step 1: 写 failing test**

```python
# tests/test_system_api.py
"""系统注册 CRUD（真 MySQL 测试库 + TestClient）。"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(test_db, monkeypatch):
    import eddplatform.api.app as app_module
    from eddplatform.store import CaseStore, SystemStore, TagStore
    monkeypatch.setattr(app_module, "store", CaseStore(db=test_db))
    monkeypatch.setattr(app_module, "tag_store", TagStore(db=test_db))
    monkeypatch.setattr(app_module, "system_store", SystemStore(db=test_db))
    return TestClient(app_module.app)


def test_systems_empty_initially(client):
    assert client.get("/api/systems").json() == []


def test_create_get_update_delete_system(client):
    r = client.post("/api/systems", json={"id": "chatagent", "name": "chatagent 2.3"})
    assert r.status_code == 201
    assert client.get("/api/systems/chatagent").json()["name"] == "chatagent 2.3"
    r = client.post("/api/systems", json={"id": "chatagent", "name": "重复"})
    assert r.status_code == 409
    r = client.put("/api/systems/chatagent", json={"id": "chatagent", "name": "改名", "owner": "leo"})
    assert r.json()["owner"] == "leo"
    assert client.delete("/api/systems/chatagent").status_code == 204
    assert client.get("/api/systems/chatagent").status_code == 404
```

- [ ] **Step 2: 跑测试确认失败**（`SystemStore` 不存在）
- [ ] **Step 3: 实现**

```python
# src/eddplatform/store/system_store.py
"""系统注册表：System 整体存 JSON 文档列。"""

from __future__ import annotations

import threading

from eddplatform.domain.models import System
from eddplatform.store.db import Db


class SystemStore:
    def __init__(self, db: Db | None = None) -> None:
        self.db = db or Db()
        self._lock = threading.Lock()

    def list(self) -> list[System]:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute("SELECT data FROM systems ORDER BY system_id")
                rows = c.fetchall()
        finally:
            conn.close()
        return [System.model_validate_json(r["data"]) for r in rows]

    def get(self, system_id: str) -> System | None:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute("SELECT data FROM systems WHERE system_id=%s", (system_id,))
                row = c.fetchone()
        finally:
            conn.close()
        return System.model_validate_json(row["data"]) if row else None

    def create(self, system: System) -> System:
        with self._lock:
            if self.get(system.id) is not None:
                raise ValueError(f"系统 {system.id} 已存在")
            conn = self.db.connect()
            try:
                with conn.cursor() as c:
                    c.execute("INSERT INTO systems(system_id, data) VALUES(%s,%s)",
                              (system.id, system.model_dump_json()))
                conn.commit()
            finally:
                conn.close()
        return system

    def update(self, system_id: str, system: System) -> System:
        with self._lock:
            if self.get(system_id) is None:
                raise KeyError(system_id)
            system.id = system_id
            conn = self.db.connect()
            try:
                with conn.cursor() as c:
                    c.execute("UPDATE systems SET data=%s WHERE system_id=%s",
                              (system.model_dump_json(), system_id))
                conn.commit()
            finally:
                conn.close()
        return system

    def delete(self, system_id: str) -> None:
        with self._lock:
            conn = self.db.connect()
            try:
                with conn.cursor() as c:
                    n = c.execute("DELETE FROM systems WHERE system_id=%s", (system_id,))
                conn.commit()
            finally:
                conn.close()
        if n == 0:
            raise KeyError(system_id)
```

`app.py`：

```python
system_store = SystemStore()

@app.get("/api/systems")
def list_systems() -> list[System]:
    return system_store.list()

@app.get("/api/systems/{system_id}")
def get_system(system_id: str) -> System:
    system = system_store.get(system_id)
    if not system:
        raise HTTPException(404, "system not found")
    return system

@app.post("/api/systems", status_code=201)
def create_system(system: System) -> System:
    try:
        return system_store.create(system)
    except ValueError as e:
        raise HTTPException(409, str(e))

@app.put("/api/systems/{system_id}")
def update_system(system_id: str, system: System) -> System:
    try:
        return system_store.update(system_id, system)
    except KeyError:
        raise HTTPException(404, "system not found")

@app.delete("/api/systems/{system_id}", status_code=204)
def delete_system(system_id: str) -> None:
    if task_store.list(system_id) or run_store.list(system_id):   # Task 6/7 接入后生效
        raise HTTPException(409, "系统下还有任务或运行记录，先清理")
    try:
        system_store.delete(system_id)
    except KeyError:
        raise HTTPException(404, "system not found")
```

（在 Task 6/7 完成前，`delete_system` 里的 task/run 校验行先注释掉，Task 7 打开。）

- [ ] **Step 4: 跑测试通过**：`.venv/bin/pytest tests/test_system_api.py -v`
- [ ] **Step 5: Commit** `feat(api,store): 系统注册 CRUD（MySQL SystemStore）`

---

### Task 6: EvalProgramStore + TaskStore + CRUD API

**Files:**
- Create: `src/eddplatform/store/eval_program_store.py`、`src/eddplatform/store/task_store.py`
- Modify: `src/eddplatform/store/__init__.py`、`src/eddplatform/api/app.py`
- Test: `tests/test_eval_program_api.py`、`tests/test_task_api.py`

**Interfaces:**
- Produces: `EvalProgramStore(db)` / `TaskStore(db)`，方法同 SystemStore 模式但按 `(system_id, id)` 分区：`list(system_id)`、`get(system_id, id)`、`create(system_id, obj)`（id 空则自动 `EP-{n:04d}` / `T-{n:04d}`）、`update(system_id, id, obj)`、`delete(system_id, id)`。
- API：`GET/POST /api/systems/{sid}/eval-programs`、`PUT/DELETE /api/systems/{sid}/eval-programs/{pid}`；tasks 同型（现有 GET/POST 改走 store，新增 PUT/DELETE）。所有端点先经 `_require_system(sid)`（不存在→404）。

- [ ] **Step 1: 写 failing tests**

```python
# tests/test_task_api.py（test_eval_program_api.py 同型，字段换成 name/git_url/ref/code）
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(test_db, monkeypatch):
    import eddplatform.api.app as app_module
    from eddplatform.store import CaseStore, EvalProgramStore, SystemStore, TagStore, TaskStore
    monkeypatch.setattr(app_module, "store", CaseStore(db=test_db))
    monkeypatch.setattr(app_module, "tag_store", TagStore(db=test_db))
    monkeypatch.setattr(app_module, "system_store", SystemStore(db=test_db))
    monkeypatch.setattr(app_module, "task_store", TaskStore(db=test_db))
    monkeypatch.setattr(app_module, "eval_program_store", EvalProgramStore(db=test_db))
    c = TestClient(app_module.app)
    c.post("/api/systems", json={"id": "sys1", "name": "系统1"})
    return c


def test_task_requires_existing_system(client):
    r = client.post("/api/systems/nope/tasks", json={"name": "t"})
    assert r.status_code == 404


def test_task_crud_persists(client, test_db):
    r = client.post("/api/systems/sys1/tasks", json={
        "name": "guide 冒烟", "system_id": "sys1",
        "preconditions": [{"kind": "start_system", "git_url": "/repo", "ref": "2.3-eval"}]})
    assert r.status_code == 201
    tid = r.json()["id"]
    assert tid.startswith("T-")
    # 持久化：新 store 实例仍读得到
    from eddplatform.store import TaskStore
    assert TaskStore(db=test_db).get("sys1", tid).name == "guide 冒烟"
    r = client.put(f"/api/systems/sys1/tasks/{tid}",
                   json={"name": "改名", "system_id": "sys1"})
    assert r.json()["name"] == "改名"
    assert client.delete(f"/api/systems/sys1/tasks/{tid}").status_code == 204
    assert client.get("/api/systems/sys1/tasks").json() == []
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现两个 store（SystemStore 模式，加 `_next_id`）+ app.py 端点**

`task_store.py` 核心（eval_program_store 同型，表名/前缀/模型不同）：

```python
# src/eddplatform/store/task_store.py
"""评估任务持久化：Task 按 (system_id, task_id) 存 JSON 文档列。"""

from __future__ import annotations

import threading

from eddplatform.domain.models import Task
from eddplatform.store.db import Db


class TaskStore:
    TABLE, ID_COL, PREFIX = "tasks", "task_id", "T"

    def __init__(self, db: Db | None = None) -> None:
        self.db = db or Db()
        self._lock = threading.Lock()

    def list(self, system_id: str) -> list[Task]:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute(f"SELECT data FROM {self.TABLE} WHERE system_id=%s ORDER BY {self.ID_COL}",
                          (system_id,))
                rows = c.fetchall()
        finally:
            conn.close()
        return [Task.model_validate_json(r["data"]) for r in rows]

    def get(self, system_id: str, task_id: str) -> Task | None:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute(f"SELECT data FROM {self.TABLE} WHERE system_id=%s AND {self.ID_COL}=%s",
                          (system_id, task_id))
                row = c.fetchone()
        finally:
            conn.close()
        return Task.model_validate_json(row["data"]) if row else None

    def create(self, system_id: str, task: Task) -> Task:
        with self._lock:
            conn = self.db.connect()
            try:
                if not task.id:
                    with conn.cursor() as c:
                        c.execute(f"SELECT COUNT(*) AS n FROM {self.TABLE} WHERE system_id=%s",
                                  (system_id,))
                        task.id = f"{self.PREFIX}-{c.fetchone()['n'] + 1:04d}"
                elif self.get(system_id, task.id) is not None:
                    raise ValueError(f"{task.id} 已存在")
                task.system_id = system_id
                with conn.cursor() as c:
                    c.execute(f"INSERT INTO {self.TABLE}(system_id, {self.ID_COL}, data) VALUES(%s,%s,%s)",
                              (system_id, task.id, task.model_dump_json()))
                conn.commit()
            finally:
                conn.close()
        return task

    def update(self, system_id: str, task_id: str, task: Task) -> Task:
        with self._lock:
            if self.get(system_id, task_id) is None:
                raise KeyError(task_id)
            task.id, task.system_id = task_id, system_id
            conn = self.db.connect()
            try:
                with conn.cursor() as c:
                    c.execute(f"UPDATE {self.TABLE} SET data=%s WHERE system_id=%s AND {self.ID_COL}=%s",
                              (task.model_dump_json(), system_id, task_id))
                conn.commit()
            finally:
                conn.close()
        return task

    def delete(self, system_id: str, task_id: str) -> None:
        with self._lock:
            conn = self.db.connect()
            try:
                with conn.cursor() as c:
                    n = c.execute(f"DELETE FROM {self.TABLE} WHERE system_id=%s AND {self.ID_COL}=%s",
                                  (system_id, task_id))
                conn.commit()
            finally:
                conn.close()
        if n == 0:
            raise KeyError(task_id)
```

注意：`create` 里 id 生成用 `COUNT(*)+1` 会在删除后撞号——改为扫描现有 id 取 max：

```python
                    with conn.cursor() as c:
                        c.execute(f"SELECT {self.ID_COL} AS i FROM {self.TABLE} WHERE system_id=%s",
                                  (system_id,))
                        nums = [int(r["i"].split("-")[1]) for r in c.fetchall()
                                if r["i"].startswith(f"{self.PREFIX}-")]
                        task.id = f"{self.PREFIX}-{(max(nums) + 1 if nums else 1):04d}"
```

app.py 辅助 + 端点：

```python
def _require_system(system_id: str) -> None:
    if system_store.get(system_id) is None:
        raise HTTPException(404, "system not found")
```

所有 `/api/systems/{sid}/...` 端点第一行调 `_require_system(system_id)`（含 cases/tags/dataset）。tasks/eval-programs 的 CRUD 端点按 store 方法一一映射（409/404 语义同 systems）。

- [ ] **Step 4: 跑测试**：`.venv/bin/pytest tests/test_task_api.py tests/test_eval_program_api.py -v`
- [ ] **Step 5: Commit** `feat(api,store): 评估程序/评估任务 CRUD 持久化（MySQL）+ 系统存在性校验`

---

### Task 7: RunStore（含 case_results）

**Files:**
- Create: `src/eddplatform/store/run_store.py`
- Modify: `src/eddplatform/store/__init__.py`
- Test: `tests/test_run_store.py`

**Interfaces:**
- Produces:
  - `RunStore(db)`：`create(RunRecord) -> RunRecord`（生成 `id = R-{uuid4.hex[:8]}`、`created_at=utcnow`）、`get(run_id) -> RunRecord | None`、`list(system_id | None) -> list[RunRecord]`（新→旧）、`finish(run_id, status, versions, outcomes, detail, finished_at)`、`add_case_result(run_id, CaseResult)`、`case_results(run_id) -> list[CaseResult]`。

- [ ] **Step 1: 写 failing test**

```python
# tests/test_run_store.py
from eddplatform.domain.models import CaseResult, RunRecord, RunStatus
from eddplatform.store.run_store import RunStore


def test_create_get_list_finish(test_db):
    rs = RunStore(db=test_db)
    run = rs.create(RunRecord(system_id="s1", task_id="T-0001", task_name="冒烟"))
    assert run.id.startswith("R-") and run.created_at is not None
    assert rs.list("s1")[0].id == run.id
    assert rs.list("other") == []
    rs.finish(run.id, RunStatus.SUCCEEDED, versions={"system": "abc"},
              outcomes=[{"kind": "start_system", "status": "ok"}], detail="")
    got = rs.get(run.id)
    assert got.status == RunStatus.SUCCEEDED and got.versions == {"system": "abc"}
    assert got.finished_at is not None


def test_case_results_roundtrip(test_db):
    rs = RunStore(db=test_db)
    run = rs.create(RunRecord(system_id="s1", task_id="T-0001"))
    rs.add_case_result(run.id, CaseResult(case_id="c1", status="passed", scores={"judge": 1.0}))
    rs.add_case_result(run.id, CaseResult(case_id="c2", status="failed", detail="工具没调"))
    got = rs.case_results(run.id)
    assert [c.case_id for c in got] == ["c1", "c2"]
    assert got[0].scores == {"judge": 1.0}
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**

```python
# src/eddplatform/store/run_store.py
"""运行记录 + 逐用例结果持久化。"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from eddplatform.domain.models import CaseResult, RunRecord, RunStatus
from eddplatform.store.db import Db


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RunStore:
    def __init__(self, db: Db | None = None) -> None:
        self.db = db or Db()
        self._lock = threading.Lock()

    def create(self, run: RunRecord) -> RunRecord:
        run.id = run.id or f"R-{uuid.uuid4().hex[:8]}"
        run.created_at = run.created_at or _now()
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute(
                    "INSERT INTO runs(run_id, system_id, task_id, status, created_at, data) "
                    "VALUES(%s,%s,%s,%s,%s,%s)",
                    (run.id, run.system_id, run.task_id, run.status.value,
                     run.created_at.replace(tzinfo=None), run.model_dump_json()),
                )
            conn.commit()
        finally:
            conn.close()
        return run

    def get(self, run_id: str) -> RunRecord | None:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute("SELECT data FROM runs WHERE run_id=%s", (run_id,))
                row = c.fetchone()
        finally:
            conn.close()
        return RunRecord.model_validate_json(row["data"]) if row else None

    def list(self, system_id: str | None = None) -> list[RunRecord]:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                if system_id:
                    c.execute("SELECT data FROM runs WHERE system_id=%s ORDER BY created_at DESC, run_id DESC",
                              (system_id,))
                else:
                    c.execute("SELECT data FROM runs ORDER BY created_at DESC, run_id DESC")
                rows = c.fetchall()
        finally:
            conn.close()
        return [RunRecord.model_validate_json(r["data"]) for r in rows]

    def finish(self, run_id: str, status: RunStatus, *, versions: dict[str, str] | None = None,
               outcomes: list[dict] | None = None, detail: str = "") -> RunRecord:
        with self._lock:
            run = self.get(run_id)
            if run is None:
                raise KeyError(run_id)
            run.status = status
            run.versions = versions or {}
            run.outcomes = outcomes or []
            run.detail = detail
            run.finished_at = _now()
            conn = self.db.connect()
            try:
                with conn.cursor() as c:
                    c.execute("UPDATE runs SET status=%s, data=%s WHERE run_id=%s",
                              (status.value, run.model_dump_json(), run_id))
                conn.commit()
            finally:
                conn.close()
        return run

    def add_case_result(self, run_id: str, result: CaseResult) -> None:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute(
                    "REPLACE INTO case_results(run_id, case_id, data) VALUES(%s,%s,%s)",
                    (run_id, result.case_id, result.model_dump_json()),
                )
            conn.commit()
        finally:
            conn.close()

    def case_results(self, run_id: str) -> list[CaseResult]:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute("SELECT data FROM case_results WHERE run_id=%s ORDER BY case_id", (run_id,))
                rows = c.fetchall()
        finally:
            conn.close()
        return [CaseResult.model_validate_json(r["data"]) for r in rows]
```

- [ ] **Step 4: 跑测试**：`.venv/bin/pytest tests/test_run_store.py -v`
- [ ] **Step 5: Commit** `feat(store): RunStore 运行记录+逐用例结果（MySQL）`

---

### Task 8: 执行触发 API + 后台回写 + runs API

**Files:**
- Modify: `src/eddplatform/api/app.py`
- Create: `src/eddplatform/api/run_service.py`
- Test: `tests/test_run_api.py`

**Interfaces:**
- Consumes: `run_task_start`（本任务在 `run_service.py` 定义）、`RunStore`、`TaskStore`、`EvalProgramStore`、`CaseStore`、Temporal `Client`。
- Produces:
  - `POST /api/systems/{sid}/tasks/{tid}/run` → 202 `RunRecord`；Temporal 连不上→503 detail=`"Temporal server 未启动（localhost:7233）"`，且不留 RunRecord。
  - `GET /api/runs?system_id=`、`GET /api/runs/{id}`（带 `case_results` 字段的详情 dict）。
  - `run_service.start_run(system_id, task, *, eval_program, cases, run_store) -> RunRecord`：组 `RunTaskInput`（含 M2 的 `eval_code`/`cases`，Task 9 定义；本任务先只传前置条件字段，Task 9 补）、`client.start_workflow`、创建 RunRecord、`asyncio.create_task(_watch(handle, run_id, run_store))`。
  - `_watch`：await handle 结果 → `run_store.finish(...)` + 逐条 `add_case_result`；异常 → `finish(FAILED, detail=str(e))`。

- [ ] **Step 1: 写 failing test**（Temporal 用假 client 打桩，重点测编排逻辑与 503 路径）

```python
# tests/test_run_api.py
import asyncio

import pytest
from fastapi.testclient import TestClient

from eddplatform.runtime.temporal.shared import OutcomeOut, RunTaskOutput


class FakeHandle:
    def __init__(self, out):
        self._out = out

    async def result(self):
        if isinstance(self._out, Exception):
            raise self._out
        return self._out


class FakeClient:
    def __init__(self, out):
        self.out = out
        self.started = []

    async def start_workflow(self, wf, arg, *, id, task_queue, execution_timeout=None):
        self.started.append((id, task_queue, arg))
        return FakeHandle(self.out)


@pytest.fixture()
def client(test_db, monkeypatch):
    import eddplatform.api.app as app_module
    from eddplatform.store import (CaseStore, EvalProgramStore, RunStore,
                                   SystemStore, TagStore, TaskStore)
    for attr, obj in [("store", CaseStore(db=test_db)), ("tag_store", TagStore(db=test_db)),
                      ("system_store", SystemStore(db=test_db)), ("task_store", TaskStore(db=test_db)),
                      ("eval_program_store", EvalProgramStore(db=test_db)),
                      ("run_store", RunStore(db=test_db))]:
        monkeypatch.setattr(app_module, attr, obj)
    c = TestClient(app_module.app)
    c.post("/api/systems", json={"id": "sys1", "name": "系统1"})
    c.post("/api/systems/sys1/tasks", json={
        "name": "冒烟", "system_id": "sys1",
        "preconditions": [{"kind": "start_system", "git_url": "/repo", "ref": "2.3-eval"}]})
    return c


def test_run_returns_503_when_temporal_down(client, monkeypatch):
    import eddplatform.api.run_service as rs

    async def no_client(_addr):
        raise OSError("connect refused")
    monkeypatch.setattr(rs, "_connect", no_client)
    r = client.post("/api/systems/sys1/tasks/T-0001/run")
    assert r.status_code == 503
    assert client.get("/api/runs").json() == []


def test_run_starts_workflow_and_watch_writes_back(client, monkeypatch):
    import eddplatform.api.run_service as rs
    out = RunTaskOutput(namespace="ns", status="up", versions={"system": "abc"},
                        outcomes=[OutcomeOut("start_system", "sys", "ok", ref="abc")])
    fake = FakeClient(out)

    async def fake_connect(_addr):
        return fake
    monkeypatch.setattr(rs, "_connect", fake_connect)
    r = client.post("/api/systems/sys1/tasks/T-0001/run")
    assert r.status_code == 202
    run_id = r.json()["id"]
    assert fake.started and fake.started[0][0] == f"edd-run-{run_id}"
    # 等后台回写（TestClient 事件循环内已排队；轮询 store）
    import time
    for _ in range(50):
        got = client.get(f"/api/runs/{run_id}").json()
        if got["status"] != "running":
            break
        time.sleep(0.1)
    assert got["status"] == "succeeded"
    assert got["versions"] == {"system": "abc"}
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现 `run_service.py` + app.py 端点**

```python
# src/eddplatform/api/run_service.py
"""执行一次 task：组 RunTaskInput → 异步 start workflow → 后台回写 RunRecord。"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import timedelta

from temporalio.client import Client

from eddplatform.domain.models import CaseResult, EvalProgram, RunRecord, RunStatus, Task
from eddplatform.runtime.temporal.shared import TASK_QUEUE, RunTaskInput, to_spec
from eddplatform.store.run_store import RunStore

TEMPORAL_ADDRESS = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")


async def _connect(address: str) -> Client:
    return await Client.connect(address)


def _namespace(system_id: str, run_id: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", f"edd-{system_id}-{run_id}".lower()).strip("-")


async def start_run(system_id: str, task: Task, *, eval_program: EvalProgram | None,
                    cases: list, run_store: RunStore) -> RunRecord:
    """提交执行。Temporal 连不上抛 ConnectionError（API 层转 503），不留运行记录。"""
    try:
        client = await _connect(TEMPORAL_ADDRESS)
    except Exception as e:  # noqa: BLE001 —— 统一视为不可达
        raise ConnectionError(f"Temporal server 未启动（{TEMPORAL_ADDRESS}）: {e}")

    run = run_store.create(RunRecord(system_id=system_id, task_id=task.id, task_name=task.name))
    inp = RunTaskInput(
        preconditions=[to_spec(pc) for pc in task.preconditions],
        namespace=_namespace(system_id, run.id),
        run_id=run.id,
        eval_code=eval_program.code if eval_program else None,
        cases=cases,
    )
    handle = await client.start_workflow(
        "RunTaskWorkflow", inp, id=f"edd-run-{run.id}", task_queue=TASK_QUEUE,
        execution_timeout=timedelta(minutes=30),
    )
    run.workflow_id = f"edd-run-{run.id}"
    run.namespace = inp.namespace
    asyncio.get_running_loop().create_task(_watch(handle, run.id, run_store))
    return run


async def _watch(handle, run_id: str, run_store: RunStore) -> None:
    try:
        out = await handle.result()
        for cr in getattr(out, "case_results", []) or []:
            d = cr if isinstance(cr, dict) else cr.__dict__
            run_store.add_case_result(run_id, CaseResult(
                case_id=d.get("case_id", ""), status=d.get("status", "error"),
                scores=d.get("scores") or {}, metrics=d.get("metrics") or {},
                detail=d.get("detail", ""), trace_url=d.get("trace_url")))
        status = RunStatus.SUCCEEDED if out.status == "up" else RunStatus.FAILED
        run_store.finish(run_id, status, versions=out.versions,
                         outcomes=[o.__dict__ for o in out.outcomes],
                         detail="" if out.status == "up" else "前置条件失败，见 outcomes")
    except Exception as e:  # noqa: BLE001 —— workflow 失败/超时都归 FAILED
        run_store.finish(run_id, RunStatus.FAILED, detail=str(e))
```

（`RunTaskInput` 的 `run_id/eval_code/cases` 字段在 Task 9 加入 shared.py；本任务与 Task 9 需连续实施，测试在 Task 9 完成后才全绿——按顺序做即可。若想本任务先绿：先在 shared.py 加这三个字段的空默认值，Task 9 只加 workflow 逻辑。**采用后者**：本任务顺带在 `shared.py` 的 `RunTaskInput` 增加：

```python
    run_id: str = ""
    eval_code: str | None = None
    cases: list["CaseSpec"] = field(default_factory=list)
```

及占位 `@dataclass class CaseSpec: case_id: str; name: str = ""; inputs: str = ""; expected: str | None = None`——Task 9 再完整化。）

app.py：

```python
from eddplatform.api import run_service
from eddplatform.store.run_store import RunStore

run_store = RunStore()

@app.post("/api/systems/{system_id}/tasks/{task_id}/run", status_code=202)
async def run_task_endpoint(system_id: str, task_id: str) -> RunRecord:
    _require_system(system_id)
    task = task_store.get(system_id, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    eval_program = None
    if task.eval_program_id:
        eval_program = eval_program_store.get(system_id, task.eval_program_id)
    cases = [run_service.case_to_spec(c) for c in store.list_cases(system_id) if c.enabled]
    try:
        return await run_service.start_run(system_id, task, eval_program=eval_program,
                                           cases=cases, run_store=run_store)
    except ConnectionError as e:
        raise HTTPException(503, str(e))

@app.get("/api/runs")
def list_runs(system_id: str | None = None) -> list[RunRecord]:
    return run_store.list(system_id)

@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = run_store.get(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {**run.model_dump(), "case_results": [c.model_dump() for c in run_store.case_results(run_id)]}
```

`run_service.case_to_spec(case) -> CaseSpec`：

```python
def case_to_spec(case) -> "CaseSpec":
    from eddplatform.runtime.temporal.shared import CaseSpec
    import json
    return CaseSpec(
        case_id=case.id, name=case.name,
        inputs=case.inputs if isinstance(case.inputs, str) else json.dumps(case.inputs, ensure_ascii=False),
        expected=(case.expected_output if isinstance(case.expected_output, str) or case.expected_output is None
                  else json.dumps(case.expected_output, ensure_ascii=False)),
    )
```

并打开 Task 5 里 `delete_system` 的 task/run 级联校验。

- [ ] **Step 4: 跑测试**：`.venv/bin/pytest tests/test_run_api.py tests/test_run_store.py -v`
- [ ] **Step 5: Commit** `feat(api): task 一键执行→Temporal 异步 start+后台回写；runs 真数据端点`

---

### Task 9: RunTaskWorkflow 逐用例 child workflow（方案 A）

**Files:**
- Modify: `src/eddplatform/runtime/temporal/shared.py`、`src/eddplatform/runtime/temporal/workflows.py`
- Test: `tests/test_temporal_case_dispatch.py`

**Interfaces:**
- Produces（评估程序仓 worker 依赖的契约，写进 shared.py docstring）:

```python
@dataclass
class CaseSpec:
    case_id: str
    name: str = ""
    inputs: str = ""                    # JSON 串或原文
    expected: str | None = None
    metadata: dict = field(default_factory=dict)

@dataclass
class RunCaseInput:
    run_id: str
    namespace: str
    case: CaseSpec

@dataclass
class CaseResultOut:
    case_id: str
    status: str = "passed"              # passed | failed | error
    scores: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    detail: str = ""
    trace_url: str | None = None
```

- `RunTaskInput` 补全：`run_id: str = ""`、`eval_code: str | None = None`、`cases: list[CaseSpec] = field(default_factory=list)`。
- `RunTaskOutput` 加 `case_results: list[CaseResultOut] = field(default_factory=list)`。
- workflow 行为：环境 `up` 且 `eval_code` 非空时，顺序对每个 case `execute_child_workflow(inp.eval_code, RunCaseInput(...), id=f"{workflow.info().workflow_id}-case-{case.case_id}", task_queue=inp.eval_code, result_type=CaseResultOut, execution_timeout=timedelta(minutes=5))`；子失败单条记 `status="error"` 不中断。

- [ ] **Step 1: 写 failing test**（in-memory Temporal，双 worker：平台队列 + 假评估程序队列）

```python
# tests/test_temporal_case_dispatch.py
"""RunTaskWorkflow 逐 case 分派 child workflow（名/队列=eval_code）——方案 A 契约测试。"""
import pytest
from temporalio import workflow
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from eddplatform.runtime.temporal.shared import (CaseResultOut, CaseSpec,
                                                 RunCaseInput, RunTaskInput, TASK_QUEUE)
from eddplatform.runtime.temporal.workflows import RunTaskWorkflow


@workflow.defn(name="demo-eval", sandboxed=False)
class FakeEvalWorkflow:
    @workflow.run
    async def run(self, inp: RunCaseInput) -> CaseResultOut:
        if inp.case.case_id == "bad":
            raise RuntimeError("判定失败")
        return CaseResultOut(case_id=inp.case.case_id, status="passed",
                             scores={"judge": 1.0}, metrics={"latency_s": 0.1})


@pytest.mark.asyncio
async def test_dispatch_cases_to_eval_code_queue():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        inp = RunTaskInput(preconditions=[], namespace="ns", run_id="R-1",
                           eval_code="demo-eval",
                           cases=[CaseSpec(case_id="c1", name="用例1", inputs="你好"),
                                  CaseSpec(case_id="bad", name="坏用例")])
        async with Worker(env.client, task_queue=TASK_QUEUE, workflows=[RunTaskWorkflow]):
            async with Worker(env.client, task_queue="demo-eval", workflows=[FakeEvalWorkflow]):
                out = await env.client.execute_workflow(
                    RunTaskWorkflow.run, inp, id="t1", task_queue=TASK_QUEUE)
    assert out.status == "up"
    by_id = {c.case_id: c for c in out.case_results}
    assert by_id["c1"].status == "passed" and by_id["c1"].scores == {"judge": 1.0}
    assert by_id["bad"].status == "error" and "判定失败" in by_id["bad"].detail
```

（若 `pytest-asyncio` 未安装：`uv add --dev pytest-asyncio`，并在 `pyproject.toml` `[tool.pytest.ini_options]` 设 `asyncio_mode = "auto"`；仓内 `test_temporal_workflow.py` 已有先例，沿用其模式。）

- [ ] **Step 2: 确认失败**（`CaseResultOut` 不存在）
- [ ] **Step 3: 实现 shared.py 数据类 + workflow 扩展**

workflows.py 在 `run_eval` 观测块之后追加：

```python
        # 逐用例分派：评估程序 worker 认领 eval_code 队列（方案 A：平台=client / 评估程序=worker）
        if out.status == "up" and inp.eval_code and inp.cases:
            for case in inp.cases:
                try:
                    r = await workflow.execute_child_workflow(
                        inp.eval_code,
                        RunCaseInput(run_id=inp.run_id, namespace=inp.namespace, case=case),
                        id=f"{workflow.info().workflow_id}-case-{case.case_id}",
                        task_queue=inp.eval_code,
                        result_type=CaseResultOut,
                        execution_timeout=timedelta(minutes=5),
                    )
                    out.case_results.append(r)
                except Exception as e:  # noqa: BLE001 —— 单用例失败不拖垮整场
                    out.case_results.append(
                        CaseResultOut(case_id=case.case_id, status="error", detail=str(e)))
```

（import 处补 `CaseResultOut, RunCaseInput`。）

- [ ] **Step 4: 跑测试**：`.venv/bin/pytest tests/test_temporal_case_dispatch.py tests/test_temporal_shared.py -v`
- [ ] **Step 5: Commit** `feat(temporal): RunTaskWorkflow 逐 case 分派 child workflow（名/队列=评估程序 code）`

---

### Task 10: chatagent evals YAML 导入

**Files:**
- Create: `src/eddplatform/api/case_yaml.py`
- Modify: `src/eddplatform/api/app.py`
- Test: `tests/test_case_yaml.py`

**Interfaces:**
- Produces: `parse_eval_yaml(text: str) -> list[Case]`；`POST /api/systems/{sid}/cases/import-yaml`（body `{"text": "...", "mode": "append"}`）→ 复用 `store.import_cases`。
- 映射约定：yaml 顶层 `group`（业务线）与 `role` 记入 tags（`group/{group}`、`role/{role}`）；每条 `cases[].id` → `Case.id`；`turns` 存 `Case.inputs`（JSON 串）；`expect` 整体存 `Case.expected_output`（dict）；yaml 条目缺 `name` 用 id。

- [ ] **Step 1: 写 failing test**

```python
# tests/test_case_yaml.py
from eddplatform.api.case_yaml import parse_eval_yaml

YAML = """
group: guide
role: guide
cases:
  - id: guide_platform_intro
    turns: [{user: "介绍一下平台"}]
    expect:
      no_tools: [execute_shop_search]
      judge: {rubric: "介绍准确"}
  - id: guide_saving
    turns: [{user: "省钱办法"}]
    expect:
      tools: [Skill]
"""


def test_parse_eval_yaml_maps_fields():
    cases = parse_eval_yaml(YAML)
    assert [c.id for c in cases] == ["guide_platform_intro", "guide_saving"]
    c = cases[0]
    assert c.name == "guide_platform_intro"
    assert "group/guide" in c.tags and "role/guide" in c.tags
    assert '"介绍一下平台"' in c.inputs or "介绍一下平台" in c.inputs
    assert c.expected_output["no_tools"] == ["execute_shop_search"]
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**

```python
# src/eddplatform/api/case_yaml.py
"""chatagent evals YAML → 平台 Case 转换。

约定：顶层 group/role 记入 tags（group/x、role/x）；turns 存 inputs（JSON 串）；
expect 整体存 expected_output（判定语义由评估程序解释，平台不理解内部结构）。
"""

from __future__ import annotations

import json

import yaml

from eddplatform.domain.models import Case


def parse_eval_yaml(text: str) -> list[Case]:
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict) or not isinstance(doc.get("cases"), list):
        raise ValueError("YAML 缺少顶层 cases 列表")
    tags = [f"group/{doc['group']}"] if doc.get("group") else []
    if doc.get("role"):
        tags.append(f"role/{doc['role']}")
    out: list[Case] = []
    for item in doc["cases"]:
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError(f"用例缺 id: {item!r}")
        out.append(Case(
            id=str(item["id"]),
            name=str(item.get("name") or item["id"]),
            description=item.get("description"),
            inputs=json.dumps(item.get("turns", []), ensure_ascii=False),
            expected_output=item.get("expect"),
            tags=list(tags),
        ))
    return out
```

app.py：

```python
class YamlImportRequest(BaseModel):
    text: str
    mode: str = "append"

@app.post("/api/systems/{system_id}/cases/import-yaml")
def import_cases_yaml(system_id: str, body: YamlImportRequest):
    _require_system(system_id)
    try:
        cases = case_yaml.parse_eval_yaml(body.text)
        res = store.import_cases(system_id, cases, mode=body.mode)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"added": res.added, "updated": res.updated, "total": res.total}
```

（`pyyaml` 已在依赖。）

- [ ] **Step 4: 跑测试**：`.venv/bin/pytest tests/test_case_yaml.py -v`
- [ ] **Step 5: Commit** `feat(api): chatagent evals YAML 导入（group/role→tags、turns→inputs、expect→expected_output）`

---

### Task 11: 后端收尾——全量测试修绿 + 启动自检

**Files:**
- Modify: `tests/test_api.py`（重写为空态断言）、受影响的 `tests/sample_fixtures.py`、`tests/release_sample.py`、`examples/` 中 import 已删模型的脚本（改 import 或加注释性弃用说明并从测试收集中排除）
- Modify: `src/eddplatform/api/app.py`（`/` 路由：`prototype/index.html` 不存在时返回 302 → `/docs`，避免误导；保留文件存在时的行为）

- [ ] **Step 1: 全量跑定位破损**：`.venv/bin/pytest tests/ -q`（列出失败清单）
- [ ] **Step 2: 逐个修**：空态断言（`GET /api/systems == []`）；删除对 sample 数据的一切引用；`test_orchestrator.py`/`test_convention.py`/`test_temporal_*.py` 不依赖被删模型，应保持绿。
- [ ] **Step 3: 启动自检**：`.venv/bin/uvicorn eddplatform.api.app:app --port 8000 &`，`curl :8000/api/health`、`curl :8000/api/systems` → `[]`；杀掉。
- [ ] **Step 4: 全量绿**：`.venv/bin/pytest tests/ -q` Expected: all pass
- [ ] **Step 5: Commit** `test: 全量测试对齐零假数据空态`

---

### Task 12: 前端改造（注册/执行/真运行记录/空态）

**Files:**
- Modify: `web/src/types.ts`、`web/src/api.ts`、`web/src/App.tsx`、`web/src/Tasks.tsx`
- Create: `web/src/Systems.tsx`、`web/src/EvalPrograms.tsx`、`web/src/Runs.tsx`
- Delete from App.tsx: 旧 `Systems`/`SysOverview` versions 表/`EvalPrograms`/`Runs`/`Evaluations`/`ComparisonView` 内联实现

**Interfaces:**
- Consumes: Task 5-10 的全部 API。
- Produces: 用户可视闭环——注册系统→注册评估程序→建/导用例→建 Task（选评估程序）→执行→Runs 列表/详情（含逐用例结果表）。

**要点（每个文件的确切改动）：**

1. `types.ts`：
   - `System` 加 `description?: string | null`；`modules` 改 `Module[] | undefined`（保持兼容，表单不填）。
   - `EvalProgram` 改为 `{ id: string; system_id: string; name: string; git_url: string; ref: string; code: string; owner?: string | null }`。
   - `Task` 加 `eval_program_id?: string | null`。
   - `RunRecord` 重定义：`{ id: string; system_id: string; task_id: string; task_name: string; status: "running" | "succeeded" | "failed"; workflow_id: string; namespace: string; versions: Record<string, string>; outcomes: {kind: string; name: string; status: string; ref?: string | null; detail?: string}[]; detail: string; created_at?: string | null; finished_at?: string | null }`。
   - 新增 `CaseResult`：`{ case_id: string; status: string; scores: Record<string, number>; metrics: Record<string, number>; detail: string; trace_url?: string | null }`；`RunDetail = RunRecord & { case_results: CaseResult[] }`。
   - 删除 `SystemVersion/Environment/Evaluation/Comparison/EvaluatorDef` 等已死类型及其 import。
2. `api.ts`：删 `versions/evaluators/environments/evaluations/comparison`；加

```typescript
  createSystem: (s: System) => send<System>("POST", "/systems", s),
  updateSystem: (id: string, s: System) => send<System>("PUT", `/systems/${id}`, s),
  deleteSystem: (id: string) => send<void>("DELETE", `/systems/${id}`),
  createEvalProgram: (sysId: string, p: Omit<EvalProgram, "id"> & { id?: string }) =>
    send<EvalProgram>("POST", `/systems/${sysId}/eval-programs`, p),
  updateEvalProgram: (sysId: string, pid: string, p: EvalProgram) =>
    send<EvalProgram>("PUT", `/systems/${sysId}/eval-programs/${pid}`, p),
  deleteEvalProgram: (sysId: string, pid: string) =>
    send<void>("DELETE", `/systems/${sysId}/eval-programs/${pid}`),
  updateTask: (sysId: string, tid: string, t: Task) =>
    send<Task>("PUT", `/systems/${sysId}/tasks/${tid}`, t),
  deleteTask: (sysId: string, tid: string) => send<void>("DELETE", `/systems/${sysId}/tasks/${tid}`),
  runTask: (sysId: string, tid: string) =>
    send<RunRecord>("POST", `/systems/${sysId}/tasks/${tid}/run`),
  runs: (sysId?: string) => get<RunRecord[]>(`/runs${sysId ? `?system_id=${sysId}` : ""}`),
  run: (id: string) => get<RunDetail>(`/runs/${id}`),
  importCasesYaml: (sysId: string, text: string, mode: "append" | "replace") =>
    send<ImportResult>("POST", `/systems/${sysId}/cases/import-yaml`, { text, mode }),
```

3. `Systems.tsx`（新文件）：列表 + 新建/编辑 modal（字段 id/name/owner/description，编辑时 id 只读）+ 删除（confirm）。空态：`暂无系统 — 点击「新建系统」注册你的第一套被评系统`。样式复用现有 `card/table/btn/modal` class（参考 `Tasks.tssx` 的 modal 结构）。
4. `EvalPrograms.tsx`（新文件）：同型 CRUD，字段 name/git_url/ref/code/owner；副标题说明 `code = Temporal RunCase workflow 名与 task queue，评估程序 worker 按它认领用例`。空态文案。
5. `Tasks.tsx`：表单加"评估程序"下拉（`api.evalPrograms`，存 `eval_program_id`，可空=仅拉环境）；表格每行加 `执行` 按钮 → `api.runTask` → 成功后提示 `已提交 R-xxxx，去「运行记录」查看`（失败弹 503 文案）；加编辑/删除按钮走 `updateTask/deleteTask`。空态文案。
6. `Runs.tsx`（新文件）：列表（id/任务/状态 Pill/版本标签/创建时间，5s 轮询 `api.runs(sysId)` 直到无 running）；点击行展开详情 `api.run(id)`：outcomes 表（前置条件/状态/ref/detail）+ case_results 表（case/状态/scores 各列/metrics/trace 链接）+ 失败 detail。空态：`暂无运行记录 — 在「评估任务」页对任务点「执行」`。
7. `App.tsx`：`Overview` 统计改为真实 `systems.length`，其余三格删掉（YAGNI）；路由把 `runs` 指向新 `Runs`（传 `sysId`）；`comparison` 视图替换为占位组件 `<Placeholder text="对比视图将随逐用例评估（M2 后）重建" />`（不引用任何 api）；`evaluations` 导航项删除；删除死 import。`SysOverview` 删掉"系统版本"表（versions API 已亡），模块表保留（空态：`该系统未登记模块——约定式部署直接用 git 仓库，无需在此配置`）。

- [ ] **Step 1: 按上述 1→7 实施**（先 types/api，再组件，最后 App.tsx 接线）
- [ ] **Step 2: 构建验证**：`cd web && npm run build` Expected: tsc + vite 零错误
- [ ] **Step 3: 手工冒烟**：uvicorn + `npm run dev`，curl 走一遍注册→建任务；浏览器无白屏（下一任务 Playwright 全面验）
- [ ] **Step 4: Commit** `feat(web): 系统/评估程序注册、任务执行、真运行记录页 + 全面空态（零假数据）`

---

### Task 13: Playwright 全流程自验 + 收尾

**Files:**
- Create: `tests/e2e_ui_check.py`（不进 pytest 默认收集：文件名不带 test_ 前缀，手动跑）

**准备：** `uv add --dev playwright && .venv/bin/playwright install chromium`。前置：MySQL 起着；`EDD_MYSQL_DB=eddplatform_uicheck .venv/bin/uvicorn eddplatform.api.app:app --port 8000` + `cd web && npm run dev`（uicheck 库起步为空 = 用户空态视角）。

- [ ] **Step 1: 写驱动脚本**

```python
# tests/e2e_ui_check.py
"""UI 全流程自验（Playwright，headless）：空态 → 注册 → 建任务 → 执行(503 文案) → 空态回归。

跑法：MySQL+uvicorn(:8000, EDD_MYSQL_DB=eddplatform_uicheck)+vite(:5173) 起着，
    .venv/bin/python tests/e2e_ui_check.py
"""
from playwright.sync_api import expect, sync_playwright

BASE = "http://localhost:5173"


def main() -> None:
    with sync_playwright() as p:
        page = p.chromium.launch().new_page()
        page.goto(BASE)
        # 1 空态
        page.get_by_text("系统管理").click()
        expect(page.get_by_text("暂无系统")).to_be_visible()
        # 2 注册系统
        page.get_by_role("button", name="新建系统").click()
        page.get_by_label("系统 ID").fill("chatagent")
        page.get_by_label("名称").fill("chatagent 2.3")
        page.get_by_role("button", name="保存").click()
        page.get_by_text("chatagent 2.3").click()
        # 3 注册评估程序
        page.get_by_text("评估程序").click()
        page.get_by_role("button", name="新建评估程序").click()
        page.get_by_label("名称").fill("chatagent 评估")
        page.get_by_label("Git 仓库").fill("/mnt/e/Documents/github/chatagent-eval")
        page.get_by_label("ref").fill("main")
        page.get_by_label("code").fill("chatagent-eval")
        page.get_by_role("button", name="保存").click()
        # 4 建用例（YAML 导入走 API 层已测；这里建一条手工用例）
        page.get_by_text("用例集").click()
        # …按 Datasets.tsx 实际控件补齐新建用例步骤…
        # 5 建任务并执行（Temporal 未启动 → 明确 503 文案，而不是崩）
        page.get_by_text("评估任务").click()
        page.get_by_role("button", name="新建评估任务").click()
        page.get_by_label("任务名").fill("guide 冒烟")
        page.get_by_role("button", name="保存").click()
        page.get_by_role("button", name="执行").click()
        expect(page.get_by_text("Temporal server 未启动")).to_be_visible()
        print("UI 自验通过")


if __name__ == "__main__":
    main()
```

（步骤 4 的控件名在实施时按 Datasets.tsx 现有 label 精确替换；脚本以"跑通并截图确认"为准，选择器细节允许在实施时校正。）

- [ ] **Step 2: 跑通脚本**（顺手 `page.screenshot()` 存 scratchpad 核对空态观感）
- [ ] **Step 3: 终验**：`.venv/bin/pytest tests/ -q` 全绿 + `cd web && npm run build` 零错误
- [ ] **Step 4: Commit** `test(e2e): Playwright UI 全流程自验脚本`

---

## Self-Review 结论

- **Spec 覆盖**：M1 五项 → Task 1-8,11,12；M2 分派/契约/结果展示/YAML → Task 9,10,12；零假数据 → Task 4,11,12,13。M2 的"对比视图重建"明确降为占位（App.tsx Placeholder），符合 spec"M2 携真实结果重建"的排序——真实对比留待 chatagent 双 ref 跑通后（M3 附近）另任务。
- **占位符扫描**：Task 13 Step 1 中"按 Datasets.tsx 实际控件补齐"是实施时对既有 UI 的探查动作，非设计空洞；其余无 TBD。
- **类型一致性**：`CaseSpec/RunCaseInput/CaseResultOut` 在 Task 8/9/12 三处引用一致；store 方法签名 Task 2/5/6/7 与 API 层调用一致。
