"""用例注册 YAML ↔ 平台 Case 转换。

用例是**纯注册记录**（name/描述/标签/轨迹/启用），评估内容（输入/期望/判定）
全部定义在评估代码仓里——YAML 里没有 turns/expect 这些字段。
兼容旧格式导入：顶层 group/role 记入 tags；旧字段 id 当 name 用；
turns/expect/code 等评估内容字段直接忽略（它们应迁去评估代码仓）。
"""

from __future__ import annotations

import yaml

from eddplatform.domain.models import Case


def case_to_yaml_doc(case: Case) -> dict:
    """Case → 单用例 YAML 文档（导出到 git 用；与 parse_eval_yaml 互逆）。"""
    item: dict = {"name": case.name}
    if case.description:
        item["description"] = case.description
    if case.tags:
        item["tags"] = list(case.tags)
    if case.trace is not None:
        item["trace"] = case.trace.model_dump(mode="json", exclude_none=True)
    if not case.enabled:
        item["enabled"] = False
    return {"cases": [item]}


def parse_eval_yaml(text: str) -> list[Case]:
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict) or not isinstance(doc.get("cases"), list):
        raise ValueError("YAML 缺少顶层 cases 列表")
    tags = [f"group/{doc['group']}"] if doc.get("group") else []
    if doc.get("role"):
        tags.append(f"role/{doc['role']}")
    out: list[Case] = []
    for item in doc["cases"]:
        if not isinstance(item, dict):
            raise ValueError(f"用例条目应为映射: {item!r}")
        # 旧格式里机器名在 id（name 是中文显示名，已废弃）——id 优先
        name = item.get("id") or item.get("name")
        if not name:
            raise ValueError(f"用例缺 name: {item!r}")
        item_tags = list(dict.fromkeys([*tags, *item.get("tags", [])]))
        out.append(Case(
            id=str(name),
            name=str(name),
            description=item.get("description"),
            tags=item_tags,
            trace=item.get("trace"),
            enabled=bool(item.get("enabled", True)),
        ))
    return out
