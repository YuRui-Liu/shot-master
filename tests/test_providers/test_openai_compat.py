from pathlib import Path
from unittest.mock import patch, MagicMock
from app.providers.base import ProviderConfig
from app.providers.openai_compat import OpenAICompatProvider


def _make_image(tmp_path: Path) -> Path:
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    return p


def test_generate_calls_chat_completions(tmp_path):
    img = _make_image(tmp_path)
    cfg = ProviderConfig(api_key="sk-test", base_url="https://x.test/v1",
                         model="gpt-4o")
    provider = OpenAICompatProvider(cfg)

    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=MagicMock(content="vision output text"))]

    with patch("app.providers.openai_compat.OpenAI") as MockClient:
        client_instance = MockClient.return_value
        client_instance.chat.completions.create.return_value = fake_resp
        out = provider.generate([img], "sys-prompt", "user-supplement")

    assert out == "vision output text"
    MockClient.assert_called_once_with(api_key="sk-test", base_url="https://x.test/v1")
    call_kwargs = client_instance.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"
    msgs = call_kwargs["messages"]
    assert msgs[0]["role"] == "system"
    assert "sys-prompt" in msgs[0]["content"]
    user_msg = msgs[1]
    assert user_msg["role"] == "user"
    # 多模态 content 是 list，含 text + image_url
    types = [item["type"] for item in user_msg["content"]]
    assert "text" in types
    assert "image_url" in types


def test_generate_with_multiple_images(tmp_path):
    imgs = []
    for i in range(3):
        p = tmp_path / f"img{i}.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        imgs.append(p)

    cfg = ProviderConfig(api_key="k", base_url="u", model="m")
    provider = OpenAICompatProvider(cfg)
    fake_resp = MagicMock(choices=[MagicMock(message=MagicMock(content="out"))])
    with patch("app.providers.openai_compat.OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = fake_resp
        provider.generate(imgs, "sp", "us")
        msgs = MockClient.return_value.chat.completions.create.call_args.kwargs["messages"]
        image_items = [i for i in msgs[1]["content"] if i["type"] == "image_url"]
        assert len(image_items) == 3


def test_available_models_returns_empty_list_by_default():
    # 不硬编码具体厂商模型，让 factory 的预设负责
    assert OpenAICompatProvider.available_models() == []
