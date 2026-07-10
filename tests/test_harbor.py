"""Harbor 客户端：httpx.MockTransport mock Harbor v2 API，无需真实 Harbor。"""

from __future__ import annotations

import httpx
import pytest

from eddplatform.domain.models import Module, SystemVersion
from eddplatform.integrations import harbor


def _mock_http(monkeypatch, handler):
    monkeypatch.setattr(harbor, "_http",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("HARBOR_URL", "https://harbor.local")
    monkeypatch.setenv("HARBOR_USER", "u")
    monkeypatch.setenv("HARBOR_TOKEN", "t")


def test_list_tags(monkeypatch, configured):
    def handler(request):
        assert "/repositories/quote/artifacts" in request.url.path
        return httpx.Response(200, json=[
            {"tags": [{"name": "2.1.0"}, {"name": "2.2.0"}]},
            {"tags": [{"name": "latest"}]},
        ])
    _mock_http(monkeypatch, handler)
    assert harbor.list_tags("insur", "quote") == ["2.1.0", "2.2.0", "latest"]


def test_artifact_digest(monkeypatch, configured):
    def handler(request):
        return httpx.Response(200, json={"digest": "sha256:abc123"})
    _mock_http(monkeypatch, handler)
    assert harbor.artifact_digest("insur", "quote", "2.2.0") == "sha256:abc123"


def test_verify_pins_all_present(monkeypatch, configured):
    def handler(request):
        return httpx.Response(200, json={"digest": "sha256:x"})   # 任何 tag 都在
    _mock_http(monkeypatch, handler)
    mods = [Module(name="quote", git_url="g"), Module(name="dialog", git_url="g")]
    ver = SystemVersion(id="v", system_id="s", label="v2",
                        module_pins={"quote": "2.2.0", "dialog": "1.0.0"})
    harbor.verify_pins(mods, ver, project="insur")     # 不抛


def test_verify_pins_reports_missing(monkeypatch, configured):
    def handler(request):
        ok = request.url.path.endswith("/2.2.0")
        return httpx.Response(200 if ok else 404, json={"digest": "sha256:x"} if ok else {})
    _mock_http(monkeypatch, handler)
    mods = [Module(name="quote", git_url="g"), Module(name="dialog", git_url="g")]
    ver = SystemVersion(id="v", system_id="s", label="v2",
                        module_pins={"quote": "2.2.0", "dialog": "9.9.9"})
    with pytest.raises(RuntimeError, match="dialog:9.9.9"):
        harbor.verify_pins(mods, ver, project="insur")


def test_verify_pins_skips_when_unconfigured(monkeypatch):
    for k in ("HARBOR_URL", "HARBOR_USER", "HARBOR_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    mods = [Module(name="quote", git_url="g")]
    ver = SystemVersion(id="v", system_id="s", label="v2", module_pins={"quote": "2.2.0"})
    harbor.verify_pins(mods, ver, project="insur")     # 未配置：安全跳过，不抛
