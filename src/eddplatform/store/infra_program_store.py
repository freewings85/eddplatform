"""基础组件库注册表：InfraProgram 按 (system_id, program_id) 存 JSON 文档列。"""

from __future__ import annotations

from eddplatform.domain.models import InfraProgram
from eddplatform.store.scoped_store import ScopedStore


class InfraProgramStore(ScopedStore[InfraProgram]):
    TABLE, ID_COL, PREFIX, MODEL = "infra_programs", "program_id", "IC", InfraProgram
