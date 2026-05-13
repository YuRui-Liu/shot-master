from pathlib import Path
from unittest.mock import patch, MagicMock
from app.providers.base import ProviderConfig
from app.providers.qwen_vl import QwenVLProvider


def _make_image(tmp_path: Path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return p


def test_qwen_generate(tmp_path):
    img = _make_image(tmp_path)
    cfg = ProviderConfig(api_key="ds-key", base_url="", model="qwen-vl-max-latest")
    provider = QwenVLProvider(cfg)

    fake_resp = MagicMock(
        status_code=200,
        output=MagicMock(choices=[MagicMock(message=MagicMock(content=[{"text": "qwen out"}]))]),
    )
    with patch("app.providers.qwen_vl.MultiModalConversation") as MockMM:
        MockMM.call.return_value = fake_resp
        out = provider.generate([img], "sys", "user")

    assert "qwen out" in out
    call_kwargs = MockMM.call.call_args.kwargs
    assert call_kwargs["api_key"] == "ds-key"
    assert call_kwargs["model"] == "qwen-vl-max-latest"
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


def test_qwen_available_models():
    models = QwenVLProvider.available_models()
    assert any("qwen" in m.lower() for m in models)
