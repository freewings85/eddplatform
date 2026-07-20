"""按 (system_id, id) 分区的 JSON 文档存储基类——EvalProgram / Task 共用。"""

from __future__ import annotations

import threading
from typing import Generic, TypeVar

from pydantic import BaseModel

from eddplatform.store.db import Db

M = TypeVar("M", bound=BaseModel)


class ScopedStore(Generic[M]):
    """子类给出 TABLE / ID_COL / PREFIX / MODEL；对象的 id、system_id 字段被本层维护。"""

    TABLE: str
    ID_COL: str
    PREFIX: str
    MODEL: type[M]

    def __init__(self, db: Db | None = None) -> None:
        self.db = db or Db()
        self._lock = threading.Lock()

    def list(self, system_id: str) -> list[M]:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute(
                    f"SELECT data FROM {self.TABLE} WHERE system_id=%s ORDER BY {self.ID_COL}",
                    (system_id,))
                rows = c.fetchall()
        finally:
            conn.close()
        return [self.MODEL.model_validate_json(r["data"]) for r in rows]

    def get(self, system_id: str, obj_id: str) -> M | None:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute(
                    f"SELECT data FROM {self.TABLE} WHERE system_id=%s AND {self.ID_COL}=%s",
                    (system_id, obj_id))
                row = c.fetchone()
        finally:
            conn.close()
        return self.MODEL.model_validate_json(row["data"]) if row else None

    def create(self, system_id: str, obj: M) -> M:
        with self._lock:
            conn = self.db.connect()
            try:
                if not obj.id:
                    obj.id = self._next_id(conn, system_id)
                elif self.get(system_id, obj.id) is not None:
                    raise ValueError(f"{obj.id} 已存在")
                obj.system_id = system_id
                with conn.cursor() as c:
                    c.execute(
                        f"INSERT INTO {self.TABLE}(system_id, {self.ID_COL}, data) VALUES(%s,%s,%s)",
                        (system_id, obj.id, obj.model_dump_json()))
                conn.commit()
            finally:
                conn.close()
        return obj

    def update(self, system_id: str, obj_id: str, obj: M) -> M:
        with self._lock:
            if self.get(system_id, obj_id) is None:
                raise KeyError(obj_id)
            obj.id = obj_id
            obj.system_id = system_id
            conn = self.db.connect()
            try:
                with conn.cursor() as c:
                    c.execute(
                        f"UPDATE {self.TABLE} SET data=%s WHERE system_id=%s AND {self.ID_COL}=%s",
                        (obj.model_dump_json(), system_id, obj_id))
                conn.commit()
            finally:
                conn.close()
        return obj

    def delete(self, system_id: str, obj_id: str) -> None:
        with self._lock:
            conn = self.db.connect()
            try:
                with conn.cursor() as c:
                    n = c.execute(
                        f"DELETE FROM {self.TABLE} WHERE system_id=%s AND {self.ID_COL}=%s",
                        (system_id, obj_id))
                conn.commit()
            finally:
                conn.close()
        if n == 0:
            raise KeyError(obj_id)

    def _next_id(self, conn, system_id: str) -> str:
        with conn.cursor() as c:
            c.execute(f"SELECT {self.ID_COL} AS i FROM {self.TABLE} WHERE system_id=%s",
                      (system_id,))
            rows = c.fetchall()
        nums = [int(r["i"].split("-")[1]) for r in rows
                if r["i"].startswith(f"{self.PREFIX}-") and r["i"].split("-")[1].isdigit()]
        return f"{self.PREFIX}-{(max(nums) + 1 if nums else 1):04d}"
