"""发布评估的确定性样例（保险报价 v1/v2）：orchestration 与 temporal 测试共用。

语义：#17 v1 挂→v2 修（改善 1、回归 0）；#102 仅 v2（对比不计入）；共有 3 例；
R-101 汇总 1→2。与 pipeline / temporal 两条编排路径的等价性断言都基于这份数据。
"""

from __future__ import annotations

from typing import Any, Callable

from eddplatform.domain.models import Case, Dataset, Module, Requirement, SystemVersion
from eddplatform.evals.engine import EqualsExpected

MODULES = [
    Module(name="quote-engine", git_url="g", image="registry/quote"),
    Module(name="dialog-agent", git_url="g", image="registry/dialog"),
]

V1 = SystemVersion(id="v1", system_id="ins", label="v1",
                   module_pins={"quote-engine": "2.1.0", "dialog-agent": "0.9.5"})
V2 = SystemVersion(id="v2", system_id="ins", label="v2",
                   module_pins={"quote-engine": "2.2.0", "dialog-agent": "1.0.0"},
                   requirement_ids=["R-101"])

DATASET = Dataset(name="保险报价", system_id="ins", cases=[
    Case(id="17", name="ev", inputs={"car": "ev"}, expected_output={"premium": 4260},
         evaluator_names=["金额校验"], requirement_ids=["R-101"]),
    Case(id="88", name="promo", inputs={"car": "petrol"}, expected_output={"premium": 3100},
         evaluator_names=["金额校验"], requirement_ids=["R-101"]),
    Case(id="91", name="claims", inputs={"car": "ev", "claims": 2}, expected_output={"premium": 5200},
         evaluator_names=["金额校验"], requirement_ids=["R-103"]),
    Case(id="102", name="v2only", inputs={"car": "ev"}, expected_output={"premium": 4260},
         applicable_versions=["v2"], evaluator_names=["金额校验"], requirement_ids=["R-101"]),
])

EVALUATORS = {"金额校验": EqualsExpected(name="金额校验", path="$.premium")}

REQUIREMENTS = [
    Requirement(id="R-101", system_id="ins", title="新能源报价修复", external_key="PROJ-2043"),
    Requirement(id="R-103", system_id="ins", title="出险延迟", external_key="PROJ-2051"),
]


def _v1(inputs: Any) -> dict:
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 3820}                    # #17 bug
    return {"premium": 5200 if inputs.get("claims") else 3100}


def _v2(inputs: Any) -> dict:
    if inputs.get("car") == "ev" and not inputs.get("claims"):
        return {"premium": 4260}                    # fixed
    return {"premium": 5200 if inputs.get("claims") else 3100}


def target_factory(label: str, manifest: dict, env_id: str) -> Callable[[Any], Any]:
    return _v1 if label == "v1" else _v2
