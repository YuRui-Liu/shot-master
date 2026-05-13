from pathlib import Path
from unittest.mock import patch, MagicMock
from app.providers.base import ProviderConfig
from app.providers.gemini import GeminiProvider


def _make_image(tmp_path: Path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return p


def test_gemini_generate(tmp_path):
    img = _make_image(tmp_path)
    cfg = ProviderConfig(api_key="g-key", base_url="", model="gemini-2.5-pro")
    provider = GeminiProvider(cfg)

    fake_resp = MagicMock(text="gemini output")
    with patch("app.providers.gemini.genai") as mock_genai:
        mock_genai.Client.return_value.models.generate_content.return_value = fake_resp
        out = provider.generate([img], "sys", "user")

    assert out == "gemini output"
    mock_genai.Client.assert_called_once_with(api_key="g-key")
    call_kwargs = mock_genai.Client.return_value.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-2.5-pro"
    contents = call_kwargs["contents"]
    # contents 应该是 list，至少含一张图 + 一段文字
    assert len(contents) >= 2


def test_gemini_available_models_lists_known():
    models = GeminiProvider.available_models()
    assert any("gemini" in m.lower() for m in models)
