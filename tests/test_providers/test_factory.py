import pytest
from drama_shot_master.providers.base import VisionProvider, ProviderConfig
from drama_shot_master.providers import factory
from drama_shot_master.config import Config


class DummyProvider(VisionProvider):
    def generate(self, images, system_prompt, user_supplement):
        return "ok"

    @classmethod
    def available_models(cls):
        return ["dummy-1"]


def test_register_and_get_provider_class():
    factory.register("dummy_test", DummyProvider)
    cls = factory.get_provider_class("dummy_test")
    assert cls is DummyProvider


def test_list_providers_includes_registered():
    factory.register("dummy_list", DummyProvider)
    names = factory.list_providers()
    assert "dummy_list" in names


def test_endpoint_presets_have_required_keys():
    presets = factory.openai_compat_presets()
    for name, info in presets.items():
        assert "base_url" in info
        assert "models" in info
        assert isinstance(info["models"], list)


def test_build_provider_with_config_picks_key():
    factory.register("dummy_build", DummyProvider)
    cfg = Config(
        api_keys={"dummy_build": "k123"},
        base_urls={"dummy_build": "https://x"},
        current_provider="dummy_build",
        current_model="dummy-1",
    )
    p = factory.build_provider(cfg, provider_name="dummy_build", model="dummy-1")
    assert isinstance(p, DummyProvider)
    assert p.config.api_key == "k123"
    assert p.config.model == "dummy-1"


def test_build_provider_raises_when_unknown():
    cfg = Config()
    with pytest.raises(KeyError, match="unknown_xxx"):
        factory.build_provider(cfg, provider_name="unknown_xxx", model="m")


def test_build_provider_raises_when_no_api_key():
    factory.register("dummy_nokey", DummyProvider)
    cfg = Config(api_keys={}, current_provider="dummy_nokey", current_model="dummy-1")
    with pytest.raises(ValueError, match="API key"):
        factory.build_provider(cfg, provider_name="dummy_nokey", model="dummy-1")
