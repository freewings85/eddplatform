"""chatagent evals YAML → 平台 Case 转换。

约定：顶层 group/role 记入 tags（group/x、role/x）；turns 存 inputs（JSON 串）；
expect 整体存 expected_output（判定语义由评估程序解释，平台不理解内部结构）。
"""

from __future__ import annotations

import json

import yaml

from eddplatform.domain.models import Case


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
        out.append(Case(
            id=str(item["id"]),
            name=str(item.get("name") or item["id"]),
            description=item.get("description"),
            inputs=json.dumps(item.get("turns", []), ensure_ascii=False),
            expected_output=item.get("expect"),
            tags=list(tags),
        ))
    return out
