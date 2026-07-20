"""评估任务持久化：Task 按 (system_id, task_id) 存 JSON 文档列。"""

from __future__ import annotations

from eddplatform.domain.models import Task
from eddplatform.store.scoped_store import ScopedStore


class TaskStore(ScopedStore[Task]):
    TABLE, ID_COL, PREFIX, MODEL = "tasks", "task_id", "T", Task
