"""用例注册 YAML ↔ Case 转换（纯注册记录：name/描述/标签/轨迹/启用）。"""
import pytest

from eddplatform.api.case_yaml import case_to_yaml_doc, parse_eval_yaml

YAML = """
cases:
  - name: guide_platform_intro
    description: 平台介绍准确
    tags: [group/guide]
  - name: guide_saving
    enabled: false
"""

LEGACY_YAML = """
group: guide
role: guide
cases:
  - id: guide_platform_intro
    name: 平台介绍准确
    turns: [{user: "介绍一下平台"}]
    expect: {judge: {rubric: "介绍准确"}}
"""


def test_parse_registry_yaml():
    cases = parse_eval_yaml(YAML)
    assert [c.name for c in cases] == ["guide_platform_intro", "guide_saving"]
    assert cases[0].id == "guide_platform_intro"        # 内部 id = name
    assert cases[0].description == "平台介绍准确"
    assert cases[0].tags == ["group/guide"]
    assert cases[1].enabled is False


def test_parse_legacy_yaml_uses_id_as_name_and_drops_eval_content():
    """旧格式：机器名在 id；turns/expect 是评估内容——导入时直接丢弃。"""
    cases = parse_eval_yaml(LEGACY_YAML)
    c = cases[0]
    assert c.name == "guide_platform_intro"
    assert "group/guide" in c.tags and "role/guide" in c.tags
    assert not hasattr(c, "inputs") and not hasattr(c, "expected_output")


def test_parse_eval_yaml_rejects_missing_cases():
    with pytest.raises(ValueError):
        parse_eval_yaml("group: guide")


def test_parse_eval_yaml_rejects_case_without_name():
    with pytest.raises(ValueError):
        parse_eval_yaml("cases:\n  - description: 没名字")


def test_registry_roundtrips_through_yaml():
    import yaml as _yaml

    from eddplatform.domain.models import Case
    c = Case(name="guide_x", description="测 X", tags=["group/guide"], enabled=False)
    doc = case_to_yaml_doc(c)
    back = parse_eval_yaml(_yaml.safe_dump(doc, allow_unicode=True))[0]
    assert (back.name, back.description, back.tags, back.enabled) == \
        ("guide_x", "测 X", ["group/guide"], False)


def test_events_from_archive_maps_trace_and_observations():
    from eddplatform.api.langfuse_client import events_from_archive
    data = {"id": "t1", "name": "会话", "observations": [
        {"id": "o1", "type": "GENERATION", "startTime": "2026-01-01T00:00:00Z",
         "model": "m", "usage": {"input": 10}},
        {"id": "o2", "type": "SPAN"}],
        "scores": [{"id": "s1", "name": "judge", "value": 1.0}]}
    events = events_from_archive(data)
    assert [e["type"] for e in events] == ["trace-create", "observation-create",
                                           "observation-create", "score-create"]
    assert events[1]["body"]["traceId"] == "t1"      # 补挂 traceId
    assert events[3]["body"]["traceId"] == "t1"
    assert "endTime" not in events[2]["body"]        # None 字段剔除
