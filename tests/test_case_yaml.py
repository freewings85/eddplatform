"""chatagent evals YAML → Case 转换。"""
import pytest

from eddplatform.api.case_yaml import parse_eval_yaml

YAML = """
group: guide
role: guide
cases:
  - id: guide_platform_intro
    turns: [{user: "介绍一下平台"}]
    expect:
      no_tools: [execute_shop_search]
      judge: {rubric: "介绍准确"}
  - id: guide_saving
    turns: [{user: "省钱办法"}]
    expect:
      tools: [Skill]
"""


def test_parse_eval_yaml_maps_fields():
    cases = parse_eval_yaml(YAML)
    assert [c.id for c in cases] == ["guide_platform_intro", "guide_saving"]
    c = cases[0]
    assert c.name == "guide_platform_intro"
    assert "group/guide" in c.tags and "role/guide" in c.tags
    assert "介绍一下平台" in c.inputs
    assert c.expected_output["no_tools"] == ["execute_shop_search"]


def test_parse_eval_yaml_rejects_missing_cases():
    with pytest.raises(ValueError):
        parse_eval_yaml("group: guide")


def test_parse_eval_yaml_rejects_case_without_id():
    with pytest.raises(ValueError):
        parse_eval_yaml("cases:\n  - turns: []")
