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
    """CREATE TABLE IF NOT EXISTS case_results (
        run_id  VARCHAR(64) NOT NULL,
        case_id VARCHAR(64) NOT NULL,
        data    JSON NOT NULL,
        PRIMARY KEY (run_id, case_id)
    ) CHARACTER SET utf8mb4""",
]

TABLES = ["cases", "tags", "systems", "system_programs", "eval_programs", "tasks", "runs",
          "case_results"]


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
