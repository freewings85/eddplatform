"""系统程序注册表：SystemProgram 按 (system_id, program_id) 存 JSON 文档列。"""

from __future__ import annotations

from eddplatform.domain.models import SystemProgram
from eddplatform.store.scoped_store import ScopedStore


class SystemProgramStore(ScopedStore[SystemProgram]):
    TABLE, ID_COL, PREFIX, MODEL = "system_programs", "program_id", "SP", SystemProgram
