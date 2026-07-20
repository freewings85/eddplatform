"""平台级设置：单行 JSON 文档（k='global'）。"""

from __future__ import annotations

from eddplatform.domain.models import GlobalSettings
from eddplatform.store.db import Db


class SettingsStore:
    KEY = "global"

    def __init__(self, db: Db | None = None) -> None:
        self.db = db or Db()

    def get(self) -> GlobalSettings:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute("SELECT v FROM settings WHERE k=%s", (self.KEY,))
                row = c.fetchone()
        finally:
            conn.close()
        return GlobalSettings.model_validate_json(row["v"]) if row else GlobalSettings()

    def put(self, settings: GlobalSettings) -> GlobalSettings:
        conn = self.db.connect()
        try:
            with conn.cursor() as c:
                c.execute("REPLACE INTO settings(k, v) VALUES(%s, %s)",
                          (self.KEY, settings.model_dump_json()))
            conn.commit()
        finally:
            conn.close()
        return settings
