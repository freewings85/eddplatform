"""用例库注册表：DatasetInfo 按 (system_id, dataset_id) 存 JSON 文档列。"""

from __future__ import annotations

from eddplatform.domain.models import DatasetInfo
from eddplatform.store.scoped_store import ScopedStore


class DatasetStore(ScopedStore[DatasetInfo]):
    TABLE, ID_COL, PREFIX, MODEL = "datasets", "dataset_id", "DS", DatasetInfo
