"""持久化层：用标准库 sqlite3 存领域对象（Case 存成 JSON 文档）。

薄：不引 ORM，pydantic 模型即事实源。见 CaseStore。
"""

from eddplatform.store.case_store import CaseStore, ImportResult

__all__ = ["CaseStore", "ImportResult"]
