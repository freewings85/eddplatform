"""运行记录 + 逐用例结果持久化。"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

from eddplatform.domain.models import CaseRunResult, RunRecord, RunStatus
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
                    c.execute("SELECT data FROM runs WHERE system_id=%s "
                              "ORDER BY created_at DESC, run_id DESC", (system_id,))
                else:
                    c.execute("SELECT data FROM runs ORDER BY created_at DESC, run_id DESC")
                rows = c.fetchall()
        finally:
            conn.close()
        return [RunRecord.model_validate_json(r["data"]) for r in rows]

    def update(self, run: RunRecord) -> RunRecord:
        """全量覆写（workflow_id/namespace 等提交后补写用）。"""
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute("UPDATE runs SET status=%s, data=%s WHERE run_id=%s",
                          (run.status.value, run.model_dump_json(), run.id))
            conn.commit()
        finally:
            conn.close()
        return run

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
            self.update(run)
        return run

    def add_case_result(self, run_id: str, result: CaseRunResult) -> None:
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

    def case_results(self, run_id: str) -> list[CaseRunResult]:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute("SELECT data FROM case_results WHERE run_id=%s ORDER BY case_id",
                          (run_id,))
                rows = c.fetchall()
        finally:
            conn.close()
        return [CaseRunResult.model_validate_json(r["data"]) for r in rows]
