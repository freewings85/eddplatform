"""基础设施薄壳：可选、import 安全、离线不可用时给可操作错误（无 k8s/Harbor 亦可）。"""

import pytest

from eddplatform.integrations import backstage, garden, harbor
from eddplatform.orchestration import temporal_workflow as tw


def test_all_shells_available_returns_bool():
    for mod in (harbor, garden, backstage, tw):
        assert isinstance(mod.available(), bool)


def test_harbor_image_ref_builds_from_env(monkeypatch):
    monkeypatch.setenv("HARBOR_URL", "registry.local")
    assert harbor.image_ref("insur", "quote", "2.2.0") == "registry.local/insur/quote:2.2.0"


def test_garden_provider_requires_cluster(monkeypatch):
    """本机无 k8s：GardenProvider 明确报错、指向 MockProvider，不假装成功。"""
    monkeypatch.setattr(garden, "available", lambda: False)
    with pytest.raises(RuntimeError, match="Garden|kubectl|集群|MockProvider"):
        garden.GardenProvider().create({"services": []})


def test_backstage_register_requires_config(monkeypatch):
    for k in ("BACKSTAGE_URL", "BACKSTAGE_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError, match="Backstage"):
        backstage.register_component({"name": "quote-engine"})
