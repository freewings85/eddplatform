"""用例（Case）持久化：MySQL + Case 存成 JSON 文档列。

表结构见 ``store/db.py``::

    cases(system_id, dataset_id, case_id, position, data JSON,
          PRIMARY KEY(system_id, dataset_id, case_id))

- 用例按 (系统, 用例库) 分区；``data`` 是 Case 的 JSON；``position`` 保序。
- 每次操作开一条连接；写操作加进程内锁，避免竞态。
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import NamedTuple, Sequence

from eddplatform.domain.models import Case
from eddplatform.store.db import Db


class ImportResult(NamedTuple):
    added: int
    updated: int
    total: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CaseStore:
    """用例存储。用例按 (system_id, dataset_id) 分区——一个系统多个用例库。"""

    def __init__(self, db: Db | None = None) -> None:
        self.db = db or Db()
        self._lock = threading.Lock()

    def _connect(self):
        return self.db.connect()

    # --- 读 --------------------------------------------------------------
    def list_cases(self, system_id: str, dataset_id: str) -> list[Case]:
        conn = self._connect()
        try:
            with conn.cursor() as c:
                c.execute(
                    "SELECT data FROM cases WHERE system_id=%s AND dataset_id=%s ORDER BY position",
                    (system_id, dataset_id),
                )
                rows = c.fetchall()
        finally:
            conn.close()
        return [Case.model_validate_json(r["data"]) for r in rows]

    def get_case(self, system_id: str, dataset_id: str, case_id: str) -> Case | None:
        conn = self._connect()
        try:
            with conn.cursor() as c:
                c.execute(
                    "SELECT data FROM cases WHERE system_id=%s AND dataset_id=%s AND case_id=%s",
                    (system_id, dataset_id, case_id),
                )
                row = c.fetchone()
        finally:
            conn.close()
        return Case.model_validate_json(row["data"]) if row else None

    # --- 写 --------------------------------------------------------------
    def add_case(self, system_id: str, dataset_id: str, case: Case) -> Case:
        """新增用例。``id`` 为空则生成（现有数字 id 最大值 + 1）。"""
        with self._lock:
            conn = self._connect()
            try:
                if not case.id:
                    case.id = self._next_id(conn, system_id, dataset_id)
                elif self._exists(conn, system_id, dataset_id, case.id):
                    raise ValueError(f"用例 {case.id} 已存在")
                now = _now()
                case.created_at = now
                case.updated_at = now
                pos = self._next_position(conn, system_id, dataset_id)
                with conn.cursor() as c:
                    c.execute(
                        "INSERT INTO cases(system_id, dataset_id, case_id, position, data) "
                        "VALUES(%s,%s,%s,%s,%s)",
                        (system_id, dataset_id, case.id, pos, case.model_dump_json()),
                    )
                conn.commit()
            finally:
                conn.close()
        return case

    def update_case(self, system_id: str, dataset_id: str, case_id: str, case: Case) -> Case:
        """全量更新。保持 id / created_at / position 不变，刷新 updated_at。"""
        with self._lock:
            conn = self._connect()
            try:
                with conn.cursor() as c:
                    c.execute(
                        "SELECT data FROM cases WHERE system_id=%s AND dataset_id=%s AND case_id=%s",
                        (system_id, dataset_id, case_id),
                    )
                    row = c.fetchone()
                if row is None:
                    raise KeyError(case_id)
                existing = Case.model_validate_json(row["data"])
                case.id = case_id
                case.created_at = existing.created_at
                case.updated_at = _now()
                with conn.cursor() as c:
                    c.execute(
                        "UPDATE cases SET data=%s WHERE system_id=%s AND dataset_id=%s AND case_id=%s",
                        (case.model_dump_json(), system_id, dataset_id, case_id),
                    )
                conn.commit()
            finally:
                conn.close()
        return case

    def delete_case(self, system_id: str, dataset_id: str, case_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                with conn.cursor() as c:
                    n = c.execute(
                        "DELETE FROM cases WHERE system_id=%s AND dataset_id=%s AND case_id=%s",
                        (system_id, dataset_id, case_id),
                    )
                conn.commit()
            finally:
                conn.close()
        if n == 0:
            raise KeyError(case_id)

    # --- 导入 / 导出 -----------------------------------------------------
    def export_cases(self, system_id: str, dataset_id: str) -> list[Case]:
        return self.list_cases(system_id, dataset_id)

    def import_cases(
        self, system_id: str, dataset_id: str, cases: Sequence[Case], mode: str = "append"
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
                    with conn.cursor() as c:
                        c.execute("DELETE FROM cases WHERE system_id=%s AND dataset_id=%s",
                                  (system_id, dataset_id))
                    for case in cases:
                        if not case.id:
                            case.id = self._next_id(conn, system_id, dataset_id)
                        now = _now()
                        case.created_at = now
                        case.updated_at = now
                        pos = self._next_position(conn, system_id, dataset_id)
                        with conn.cursor() as c:
                            c.execute(
                                "INSERT INTO cases(system_id, dataset_id, case_id, position, data) "
                                "VALUES(%s,%s,%s,%s,%s)",
                                (system_id, dataset_id, case.id, pos, case.model_dump_json()),
                            )
                        added += 1
                else:  # append / upsert
                    for case in cases:
                        row = None
                        if case.id:
                            with conn.cursor() as c:
                                c.execute(
                                    "SELECT data, position FROM cases "
                                    "WHERE system_id=%s AND dataset_id=%s AND case_id=%s",
                                    (system_id, dataset_id, case.id),
                                )
                                row = c.fetchone()
                        now = _now()
                        if row is not None:
                            existing = Case.model_validate_json(row["data"])
                            case.created_at = existing.created_at
                            case.updated_at = now
                            with conn.cursor() as c:
                                c.execute(
                                    "UPDATE cases SET data=%s "
                                    "WHERE system_id=%s AND dataset_id=%s AND case_id=%s",
                                    (case.model_dump_json(), system_id, dataset_id, case.id),
                                )
                            updated += 1
                        else:
                            if not case.id:
                                case.id = self._next_id(conn, system_id, dataset_id)
                            case.created_at = now
                            case.updated_at = now
                            pos = self._next_position(conn, system_id, dataset_id)
                            with conn.cursor() as c:
                                c.execute(
                                    "INSERT INTO cases(system_id, dataset_id, case_id, position, data) "
                                    "VALUES(%s,%s,%s,%s,%s)",
                                    (system_id, dataset_id, case.id, pos, case.model_dump_json()),
                                )
                            added += 1
                conn.commit()
                with conn.cursor() as c:
                    c.execute(
                        "SELECT COUNT(*) AS n FROM cases WHERE system_id=%s AND dataset_id=%s",
                        (system_id, dataset_id),
                    )
                    total = c.fetchone()["n"]
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
                with conn.cursor() as c:
                    c.execute(
                        "SELECT dataset_id, case_id, data FROM cases WHERE system_id=%s",
                        (system_id,)
                    )
                    rows = c.fetchall()
                for row in rows:
                    case = Case.model_validate_json(row["data"])
                    new_tags = [self._rewrite_one(t, old_path, new_path) for t in case.tags]
                    if new_tags != case.tags:
                        case.tags = new_tags
                        with conn.cursor() as c:
                            c.execute(
                                "UPDATE cases SET data=%s "
                                "WHERE system_id=%s AND dataset_id=%s AND case_id=%s",
                                (case.model_dump_json(), system_id, row["dataset_id"],
                                 row["case_id"]),
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

    # --- 内部 ------------------------------------------------------------
    def _exists(self, conn, system_id: str, dataset_id: str, case_id: str) -> bool:
        with conn.cursor() as c:
            c.execute(
                "SELECT 1 FROM cases WHERE system_id=%s AND dataset_id=%s AND case_id=%s",
                (system_id, dataset_id, case_id),
            )
            return c.fetchone() is not None

    def _next_id(self, conn, system_id: str, dataset_id: str) -> str:
        with conn.cursor() as c:
            c.execute("SELECT case_id FROM cases WHERE system_id=%s AND dataset_id=%s",
                      (system_id, dataset_id))
            rows = c.fetchall()
        nums = [int(r["case_id"]) for r in rows if str(r["case_id"]).isdigit()]
        return str(max(nums) + 1) if nums else "1"

    def _next_position(self, conn, system_id: str, dataset_id: str) -> int:
        with conn.cursor() as c:
            c.execute("SELECT MAX(position) AS m FROM cases WHERE system_id=%s AND dataset_id=%s",
                      (system_id, dataset_id))
            row = c.fetchone()
        return 0 if row["m"] is None else int(row["m"]) + 1
