from pathlib import Path
from unittest.mock import patch, MagicMock
from drama_shot_master.providers.base import ProviderConfig
from drama_shot_master.providers.anthropic import AnthropicProvider


def _make_image(tmp_path: Path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return p


def test_anthropic_generate(tmp_path):
    img = _make_image(tmp_path)
    cfg = ProviderConfig(api_key="sk-ant-x", base_url="", model="claude-opus-4")
    provider = AnthropicProvider(cfg)

    fake_text_block = MagicMock(text="claude output")
    fake_resp = MagicMock(content=[fake_text_block])

    with patch("drama_shot_master.providers.anthropic.Anthropic") as MockClient:
        MockClient.return_value.messages.create.return_value = fake_resp
        out = provider.generate([img], "sys-prompt", "user-supp")

    assert out == "claude output"
    MockClient.assert_called_once_with(api_key="sk-ant-x")
    call_kwargs = MockClient.return_value.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-opus-4"
    assert call_kwargs["system"] == "sys-prompt"
    msgs = call_kwargs["messages"]
    user_msg = msgs[0]
    types = [item["type"] for item in user_msg["content"]]
    assert "text" in types
    assert "image" in types


def test_anthropic_available_models():
    models = AnthropicProvider.available_models()
    assert any("claude" in m for m in models)
