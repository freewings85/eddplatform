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
    """CREATE TABLE IF NOT EXISTS datasets (
        system_id  VARCHAR(64) NOT NULL,
        dataset_id VARCHAR(64) NOT NULL,
        data       JSON NOT NULL,
        PRIMARY KEY (system_id, dataset_id)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS cases (
        system_id  VARCHAR(64) NOT NULL,
        dataset_id VARCHAR(64) NOT NULL,
        case_id    VARCHAR(64) NOT NULL,
        position   INT NOT NULL,
        data       JSON NOT NULL,
        PRIMARY KEY (system_id, dataset_id, case_id)
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
    """CREATE TABLE IF NOT EXISTS system_programs (
        system_id  VARCHAR(64) NOT NULL,
        program_id VARCHAR(64) NOT NULL,
        data       JSON NOT NULL,
        PRIMARY KEY (system_id, program_id)
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
    """CREATE TABLE IF NOT EXISTS settings (
        k VARCHAR(64) NOT NULL,
        v JSON NOT NULL,
        PRIMARY KEY (k)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS case_results (
        run_id  VARCHAR(64) NOT NULL,
        case_id VARCHAR(64) NOT NULL,
        data    JSON NOT NULL,
        PRIMARY KEY (run_id, case_id)
    ) CHARACTER SET utf8mb4""",
    """CREATE TABLE IF NOT EXISTS run_logs (
        id     BIGINT NOT NULL AUTO_INCREMENT,
        run_id VARCHAR(64) NOT NULL,
        ts     DATETIME(3) NOT NULL,
        line   TEXT NOT NULL,
        PRIMARY KEY (id),
        KEY idx_run_logs_run (run_id, id)
    ) CHARACTER SET utf8mb4""",
]

TABLES = ["cases", "datasets", "tags", "systems", "system_programs", "eval_programs", "tasks",
          "runs", "case_results", "run_logs", "settings"]


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
            self._migrate(conn)
            conn.commit()
        finally:
            conn.close()

    def _migrate(self, conn) -> None:
        """旧库就地迁移：cases 表补 dataset_id 分区，存量用例归入「默认用例库」。"""
        with conn.cursor() as c:
            c.execute("SHOW COLUMNS FROM cases LIKE 'dataset_id'")
            if c.fetchone():
                return
            c.execute("ALTER TABLE cases ADD COLUMN dataset_id VARCHAR(64) NOT NULL "
                      "DEFAULT 'DS-0001' AFTER system_id")
            c.execute("ALTER TABLE cases DROP PRIMARY KEY, "
                      "ADD PRIMARY KEY (system_id, dataset_id, case_id)")
            c.execute("SELECT DISTINCT system_id AS s FROM cases")
            sids = [r["s"] for r in c.fetchall()]
        import json
        with conn.cursor() as c:
            for sid in sids:
                data = json.dumps({"id": "DS-0001", "system_id": sid,
                                   "name": "默认用例库", "description": None},
                                  ensure_ascii=False)
                c.execute("INSERT IGNORE INTO datasets(system_id, dataset_id, data) "
                          "VALUES(%s, 'DS-0001', %s)", (sid, data))

    def truncate_all(self) -> None:
        conn = self.connect()
        try:
            with conn.cursor() as c:
                for t in TABLES:
                    c.execute(f"TRUNCATE TABLE `{t}`")
            conn.commit()
        finally:
            conn.close()
