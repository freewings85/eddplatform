"""Langfuse 轨迹链接解析：URL → trace id（表单「从链接导入」的入口）。"""
import pytest

from eddplatform.api.langfuse_client import LangfuseError, trace_id_from_url


@pytest.mark.parametrize("url,expect", [
    ("http://localhost:3100/project/eddplatform/traces/tr-abc123", "tr-abc123"),
    ("http://localhost:3100/project/p1/traces/tr-abc?observation=o1", "tr-abc"),
    ("https://cloud.langfuse.com/trace/0xdeadbeef", "0xdeadbeef"),
    ("  http://h/project/p/traces/id-with-空格前后  ", "id-with-空格前后"),
    # 列表页「peek 预览」链接：id 在查询参数里
    ("http://127.0.0.1:3100/project/cmrdefzdp000xnx07w4094xbl/traces"
     "?peek=1abf4893a4d4c9baf0c157625755ed9f&timestamp=2026-07-20T08%3A52%3A17.959Z",
     "1abf4893a4d4c9baf0c157625755ed9f"),
])
def test_trace_id_from_url(url, expect):
    assert trace_id_from_url(url) == expect


@pytest.mark.parametrize("bad", [
    "http://localhost:3100/project/eddplatform",   # 没有 traces 段
    "http://localhost:3100/project/p/traces/",     # traces 后为空
    "not-a-url",
])
def test_trace_id_from_url_rejects(bad):
    with pytest.raises(LangfuseError):
        trace_id_from_url(bad)
