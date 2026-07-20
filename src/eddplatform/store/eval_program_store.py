"""评估程序注册表：EvalProgram 按 (system_id, program_id) 存 JSON 文档列。"""

from __future__ import annotations

from eddplatform.domain.models import EvalProgram
from eddplatform.store.scoped_store import ScopedStore


class EvalProgramStore(ScopedStore[EvalProgram]):
    TABLE, ID_COL, PREFIX, MODEL = "eval_programs", "program_id", "EP", EvalProgram
