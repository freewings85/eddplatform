"""chatagent evals YAML → 平台 Case 转换。

约定：顶层 group/role 记入 tags（group/x、role/x）；turns 存 inputs（JSON 串）；
expect 整体存 expected_output（判定语义由评估程序解释，平台不理解内部结构）。
"""

from __future__ import annotations

import json

import yaml

from eddplatform.domain.models import Case


def case_to_yaml_doc(case: Case) -> dict:
    """Case → 单用例 YAML 文档（导出到 git 用；与 parse_eval_yaml 互逆）。"""
    turns: object = []
    if isinstance(case.inputs, str):
        try:
            turns = json.loads(case.inputs) if case.inputs.strip() else []
        except ValueError:
            turns = [{"user": case.inputs}]
    else:
        turns = case.inputs
    item: dict = {"id": case.id, "name": case.name}
    if case.code:
        item["code"] = case.code
    if case.description:
        item["description"] = case.description
    if case.tags:
        item["tags"] = list(case.tags)
    item["turns"] = turns
    if case.expected_output is not None:
        item["expect"] = case.expected_output
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
        if not isinstance(item, dict) or not item.get("id"):
            raise ValueError(f"用例缺 id: {item!r}")
        item_tags = list(dict.fromkeys([*tags, *item.get("tags", [])]))
        out.append(Case(
            id=str(item["id"]),
            name=str(item.get("name") or item["id"]),
            description=item.get("description"),
            code=item.get("code"),
            inputs=json.dumps(item.get("turns", []), ensure_ascii=False),
            expected_output=item.get("expect"),
            tags=item_tags,
            trace=item.get("trace"),
            enabled=bool(item.get("enabled", True)),
        ))
    return out
