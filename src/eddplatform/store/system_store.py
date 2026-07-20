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
