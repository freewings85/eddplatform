"""运行控制台日志：一次运行的逐行执行日志（Jenkins 控制台输出的等价物）。

生产者：Temporal 活动（clone/构建/导镜像/helm/队列预检）与 workflow（逐用例分派）、
API 侧（提交/收尾）。消费者：``GET /api/runs/{id}/logs`` 增量轮询。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from eddplatform.store.db import Db

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")   # 工具输出里的终端颜色码（k3d 等）


class RunLogStore:
    def __init__(self, db: Db | None = None) -> None:
        self.db = db or Db()

    def append(self, run_id: str, text: str) -> None:
        """追加日志。``text`` 可含多行——按行拆成多条记录（前端逐行渲染）。"""
        lines = [_ANSI.sub("", ln) for ln in text.splitlines()] or [""]
        ts = datetime.now(timezone.utc).replace(tzinfo=None)
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.executemany(
                    "INSERT INTO run_logs(run_id, ts, line) VALUES(%s,%s,%s)",
                    [(run_id, ts, ln[:60000]) for ln in lines],
                )
            conn.commit()
        finally:
            conn.close()

    def list(self, run_id: str, after: int = 0) -> list[dict]:
        """按 id 增量取（``after`` = 上次拿到的最大 id，0=从头）。"""
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute(
                    "SELECT id, ts, line FROM run_logs WHERE run_id=%s AND id>%s ORDER BY id",
                    (run_id, after),
                )
                rows = c.fetchall()
        finally:
            conn.close()
        return [{"id": r["id"], "ts": r["ts"].isoformat() + "Z", "line": r["line"]}
                for r in rows]
