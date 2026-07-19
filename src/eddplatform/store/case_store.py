"""用例（Case）持久化：sqlite3 + Case 存成 JSON 文档列。

表结构::

    cases(system_id TEXT, case_id TEXT, position INTEGER, data TEXT,
          PRIMARY KEY(system_id, case_id))

- ``data`` 是 Case 的 JSON；``position`` 保序。
- 每次操作开一条连接（sqlite 文件足够快），写操作加进程内锁，避免竞态。
- DB 路径默认 ``data/eddplatform.db``，可用环境变量 ``EDDPLATFORM_DB`` 覆盖。
"""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, NamedTuple, Sequence

from eddplatform.domain.models import Case

DEFAULT_DB = "data/eddplatform.db"


class ImportResult(NamedTuple):
    added: int
    updated: int
    total: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CaseStore:
    """用例存储。一系统一 dataset：用例按 ``system_id`` 分区。"""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or os.environ.get("EDDPLATFORM_DB", DEFAULT_DB)
        self._lock = threading.Lock()
        parent = Path(self.db_path).parent
        if str(parent):
            parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # --- 连接 / 建表 ------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS cases (
                    system_id TEXT NOT NULL,
                    case_id   TEXT NOT NULL,
                    position  INTEGER NOT NULL,
                    data      TEXT NOT NULL,
                    PRIMARY KEY (system_id, case_id)
                )"""
            )
            conn.commit()
        finally:
            conn.close()

    # --- 读 --------------------------------------------------------------
    def list_cases(self, system_id: str) -> list[Case]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT data FROM cases WHERE system_id=? ORDER BY position",
                (system_id,),
            ).fetchall()
        finally:
            conn.close()
        return [Case.model_validate_json(r["data"]) for r in rows]

    def get_case(self, system_id: str, case_id: str) -> Case | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT data FROM cases WHERE system_id=? AND case_id=?",
                (system_id, case_id),
            ).fetchone()
        finally:
            conn.close()
        return Case.model_validate_json(row["data"]) if row else None

    # --- 写 --------------------------------------------------------------
    def add_case(self, system_id: str, case: Case) -> Case:
        """新增用例。``id`` 为空则生成（现有数字 id 最大值 + 1）。"""
        with self._lock:
            conn = self._connect()
            try:
                if not case.id:
                    case.id = self._next_id(conn, system_id)
                elif self._exists(conn, system_id, case.id):
                    raise ValueError(f"用例 {case.id} 已存在")
                now = _now()
                case.created_at = now
                case.updated_at = now
                pos = self._next_position(conn, system_id)
                conn.execute(
                    "INSERT INTO cases(system_id, case_id, position, data) VALUES(?,?,?,?)",
                    (system_id, case.id, pos, case.model_dump_json()),
                )
                conn.commit()
            finally:
                conn.close()
        return case

    def update_case(self, system_id: str, case_id: str, case: Case) -> Case:
        """全量更新。保持 id / created_at / position 不变，刷新 updated_at。"""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT data FROM cases WHERE system_id=? AND case_id=?",
                    (system_id, case_id),
                ).fetchone()
                if row is None:
                    raise KeyError(case_id)
                existing = Case.model_validate_json(row["data"])
                case.id = case_id
                case.created_at = existing.created_at
                case.updated_at = _now()
                conn.execute(
                    "UPDATE cases SET data=? WHERE system_id=? AND case_id=?",
                    (case.model_dump_json(), system_id, case_id),
                )
                conn.commit()
            finally:
                conn.close()
        return case

    def delete_case(self, system_id: str, case_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "DELETE FROM cases WHERE system_id=? AND case_id=?",
                    (system_id, case_id),
                )
                if cur.rowcount == 0:
                    raise KeyError(case_id)
                conn.commit()
            finally:
                conn.close()

    # --- 导入 / 导出 -----------------------------------------------------
    def export_cases(self, system_id: str) -> list[Case]:
        return self.list_cases(system_id)

    def import_cases(
        self, system_id: str, cases: Sequence[Case], mode: str = "append"
    ) -> ImportResult:
        """导入用例。

        - ``mode="append"``：按 id upsert（有则更新、无则新增），保留其它用例。
        - ``mode="replace"``：清空该系统全部用例后重建。
        """
        if mode not in ("append", "replace"):
            raise ValueError(f"未知导入模式：{mode}")
        added = updated = 0
        with self._lock:
            conn = self._connect()
            try:
                if mode == "replace":
                    conn.execute("DELETE FROM cases WHERE system_id=?", (system_id,))
                    for case in cases:
                        if not case.id:
                            case.id = self._next_id(conn, system_id)
                        now = _now()
                        case.created_at = now
                        case.updated_at = now
                        pos = self._next_position(conn, system_id)
                        conn.execute(
                            "INSERT INTO cases(system_id, case_id, position, data) "
                            "VALUES(?,?,?,?)",
                            (system_id, case.id, pos, case.model_dump_json()),
                        )
                        added += 1
                else:  # append / upsert
                    for case in cases:
                        row = None
                        if case.id:
                            row = conn.execute(
                                "SELECT data, position FROM cases "
                                "WHERE system_id=? AND case_id=?",
                                (system_id, case.id),
                            ).fetchone()
                        now = _now()
                        if row is not None:
                            existing = Case.model_validate_json(row["data"])
                            case.created_at = existing.created_at
                            case.updated_at = now
                            conn.execute(
                                "UPDATE cases SET data=? WHERE system_id=? AND case_id=?",
                                (case.model_dump_json(), system_id, case.id),
                            )
                            updated += 1
                        else:
                            if not case.id:
                                case.id = self._next_id(conn, system_id)
                            case.created_at = now
                            case.updated_at = now
                            pos = self._next_position(conn, system_id)
                            conn.execute(
                                "INSERT INTO cases(system_id, case_id, position, data) "
                                "VALUES(?,?,?,?)",
                                (system_id, case.id, pos, case.model_dump_json()),
                            )
                            added += 1
                conn.commit()
                total = conn.execute(
                    "SELECT COUNT(*) AS n FROM cases WHERE system_id=?", (system_id,)
                ).fetchone()["n"]
            finally:
                conn.close()
        return ImportResult(added=added, updated=updated, total=total)

    # --- 标签维护 --------------------------------------------------------
    def rewrite_tag_prefix(self, system_id: str, old_path: str, new_path: str) -> int:
        """把 case 标签里等于 old_path、或以 ``old_path + "/"`` 开头的前缀改成 new_path。

        用于标签重命名后保持 case 上的路径一致。返回受影响的用例数（不动 updated_at）。
        """
        if old_path == new_path:
            return 0
        changed = 0
        with self._lock:
            conn = self._connect()
            try:
                rows = conn.execute(
                    "SELECT case_id, data FROM cases WHERE system_id=?", (system_id,)
                ).fetchall()
                for row in rows:
                    case = Case.model_validate_json(row["data"])
                    new_tags = [self._rewrite_one(t, old_path, new_path) for t in case.tags]
                    if new_tags != case.tags:
                        case.tags = new_tags
                        conn.execute(
                            "UPDATE cases SET data=? WHERE system_id=? AND case_id=?",
                            (case.model_dump_json(), system_id, row["case_id"]),
                        )
                        changed += 1
                conn.commit()
            finally:
                conn.close()
        return changed

    @staticmethod
    def _rewrite_one(tag: str, old_path: str, new_path: str) -> str:
        if tag == old_path:
            return new_path
        if tag.startswith(old_path + "/"):
            return new_path + tag[len(old_path):]
        return tag

    # --- 播种 ------------------------------------------------------------
    def seed_if_empty(self, system_id: str, cases: Iterable[Case]) -> None:
        """该系统还没有任何用例时，用给定用例播种（幂等）。"""
        if self.list_cases(system_id):
            return
        self.import_cases(system_id, [c.model_copy(deep=True) for c in cases], mode="replace")

    # --- 内部 ------------------------------------------------------------
    def _exists(self, conn: sqlite3.Connection, system_id: str, case_id: str) -> bool:
        return (
            conn.execute(
                "SELECT 1 FROM cases WHERE system_id=? AND case_id=?",
                (system_id, case_id),
            ).fetchone()
            is not None
        )

    def _next_id(self, conn: sqlite3.Connection, system_id: str) -> str:
        rows = conn.execute(
            "SELECT case_id FROM cases WHERE system_id=?", (system_id,)
        ).fetchall()
        nums = [int(r["case_id"]) for r in rows if str(r["case_id"]).isdigit()]
        return str(max(nums) + 1) if nums else "1"

    def _next_position(self, conn: sqlite3.Connection, system_id: str) -> int:
        row = conn.execute(
            "SELECT MAX(position) AS m FROM cases WHERE system_id=?", (system_id,)
        ).fetchone()
        return 0 if row["m"] is None else int(row["m"]) + 1
