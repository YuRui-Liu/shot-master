import pytest
from pathlib import Path
from drama_shot_master.providers.base import VisionProvider, ProviderConfig, encode_image_b64


class FakeProvider(VisionProvider):
    def generate(self, images, system_prompt, user_supplement):
        return f"len={len(images)} sp={system_prompt[:5]} us={user_supplement[:5]}"

    @classmethod
    def available_models(cls):
        return ["fake-1", "fake-2"]


def test_provider_config_dataclass():
    cfg = ProviderConfig(api_key="k", base_url="u", model="m")
    assert cfg.api_key == "k"
    assert cfg.model == "m"


def test_provider_interface(tmp_path):
    p = FakeProvider(ProviderConfig(api_key="k", base_url="", model="fake-1"))
    out = p.generate([tmp_path / "a.png"], "system hello", "user hi")
    assert "len=1" in out


def test_encode_image_b64(tmp_path):
    p = tmp_path / "x.png"
    # 1x1 透明 PNG
    p.write_bytes(bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
    ))
    s = encode_image_b64(p)
    assert s.startswith("iVBORw0KGgo") or len(s) > 20
