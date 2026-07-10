"""Backstage 客户端：descriptor 是纯函数（永远可测）；注册用 httpx.MockTransport。"""

from __future__ import annotations

import httpx
import pytest

from eddplatform.domain.models import Module, System
from eddplatform.integrations import backstage


def test_component_descriptor_from_module():
    m = Module(name="quote-engine", git_url="git@git.co/insur/quote.git", owner="张三")
    d = backstage.component_descriptor(m)
    assert d["kind"] == "Component"
    assert d["metadata"]["name"] == "quote-engine"
    assert d["spec"]["type"] == "service"
    assert d["spec"]["owner"] == "张三"
    assert d["metadata"]["annotations"]["backstage.io/source-location"] == \
        "url:git@git.co/insur/quote.git"


def test_component_descriptor_defaults_owner():
    d = backstage.component_descriptor(Module(name="x", git_url="g"))
    assert d["spec"]["owner"] == "unknown"


def test_system_descriptor():
    s = System(id="insurance", name="保险报价系统", owner="李雷")
    d = backstage.system_descriptor(s)
    assert d["kind"] == "System"
    assert d["metadata"]["name"] == "insurance"
    assert d["spec"]["owner"] == "李雷"


def test_register_location_posts(monkeypatch):
    monkeypatch.setenv("BACKSTAGE_URL", "https://backstage.local")
    monkeypatch.setenv("BACKSTAGE_TOKEN", "tok")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(201, json={"location": {"target": "catalog-info.yaml"}})

    monkeypatch.setattr(backstage, "_http",
                        lambda: httpx.Client(transport=httpx.MockTransport(handler),
                                              headers={"Authorization": "Bearer tok"}))
    out = backstage.register_location("https://git.local/catalog-info.yaml")
    assert out["location"]["target"] == "catalog-info.yaml"
    assert seen["url"].endswith("/api/catalog/locations")
    assert seen["auth"] == "Bearer tok"


def test_register_component_requires_config(monkeypatch):
    for k in ("BACKSTAGE_URL", "BACKSTAGE_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="Backstage"):
        backstage.register_component({"name": "quote-engine"})
