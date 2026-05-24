"""ComfyUIUpscaler 单测（mock httpx，不连真实服务）。"""
from __future__ import annotations

import httpx
import pytest

from app.providers.comfyui_upscaler import (
    ComfyUIUpscaler, ComfyUIUnavailable,
)


def _mock_transport(handler):
    """构造 httpx MockTransport，把所有请求交给 handler 处理。"""
    return httpx.MockTransport(handler)


@pytest.fixture
def fake_object_info():
    """ComfyUI /object_info/UpscaleModelLoader 标准响应（按真实 API 形状）。"""
    return {
        "UpscaleModelLoader": {
            "input": {
                "required": {
                    "model_name": [
                        ["4x-UltraSharp.pth", "RealESRGAN_x4plus.pth", "ESRGAN_4x.pth"]
                    ]
                }
            }
        }
    }


def test_list_models_happy_path(fake_object_info, monkeypatch):
    def handler(req):
        assert req.method == "GET"
        assert req.url.path == "/object_info/UpscaleModelLoader"
        return httpx.Response(200, json=fake_object_info)

    up = ComfyUIUpscaler("http://test:8188")
    monkeypatch.setattr(up, "_client",
                        httpx.Client(transport=_mock_transport(handler)))
    assert up.list_models() == [
        "4x-UltraSharp.pth", "RealESRGAN_x4plus.pth", "ESRGAN_4x.pth"]


def test_list_models_empty_when_node_missing(monkeypatch):
    def handler(req):
        return httpx.Response(200, json={})    # 不含 UpscaleModelLoader

    up = ComfyUIUpscaler("http://test:8188")
    monkeypatch.setattr(up, "_client",
                        httpx.Client(transport=_mock_transport(handler)))
    assert up.list_models() == []


def test_list_models_raises_unavailable_on_connect_error(monkeypatch):
    def handler(req):
        raise httpx.ConnectError("Connection refused")

    up = ComfyUIUpscaler("http://test:8188")
    monkeypatch.setattr(up, "_client",
                        httpx.Client(transport=_mock_transport(handler)))
    with pytest.raises(ComfyUIUnavailable):
        up.list_models()


def test_list_models_raises_unavailable_on_5xx(monkeypatch):
    def handler(req):
        return httpx.Response(500, text="ComfyUI internal error")

    up = ComfyUIUpscaler("http://test:8188")
    monkeypatch.setattr(up, "_client",
                        httpx.Client(transport=_mock_transport(handler)))
    with pytest.raises(ComfyUIUnavailable):
        up.list_models()


def test_base_url_trailing_slash_normalized():
    up = ComfyUIUpscaler("http://test:8188/")
    assert up.base_url == "http://test:8188"
