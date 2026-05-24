"""ComfyUIUpscaler 单测（mock httpx，不连真实服务）。"""
from __future__ import annotations

import io
import re

import httpx
import pytest
from PIL import Image

from drama_shot_master.providers.comfyui_upscaler import (
    ComfyUIUpscaler, ComfyUIUnavailable, ComfyUIUpscaleError,
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


def _png_bytes(w=64, h=64, color=(100, 100, 100)):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


class _ComfyUIScenario:
    """可编程的 ComfyUI mock 响应序列。"""

    def __init__(self, history_responses):
        self.history_responses = list(history_responses)
        self.upload_calls = []
        self.prompt_calls = []
        self.history_calls = 0
        self.view_calls = []

    def handler(self, req):
        path = req.url.path
        if path == "/upload/image":
            self.upload_calls.append(req)
            return httpx.Response(200, json={
                "name": "spb_uploaded.png", "subfolder": "", "type": "input"})
        if path == "/prompt":
            self.prompt_calls.append(req)
            return httpx.Response(200, json={"prompt_id": "test-prompt-1"})
        if path.startswith("/history/"):
            idx = min(self.history_calls, len(self.history_responses) - 1)
            self.history_calls += 1
            return httpx.Response(200, json=self.history_responses[idx])
        if path == "/view":
            self.view_calls.append(req)
            return httpx.Response(200, content=_png_bytes(256, 256),
                                   headers={"Content-Type": "image/png"})
        return httpx.Response(404)


def _make_upscaler_with_scenario(scenario, timeout=2):
    up = ComfyUIUpscaler("http://test:8188", timeout=timeout)
    up._client = httpx.Client(transport=httpx.MockTransport(scenario.handler))
    return up


def _outputs_ready():
    return {
        "test-prompt-1": {
            "outputs": {
                "4": {"images": [
                    {"filename": "spb_upscale_001.png",
                     "subfolder": "", "type": "output"}
                ]}
            }
        }
    }


def test_upscale_happy_path():
    scen = _ComfyUIScenario([_outputs_ready()])
    up = _make_upscaler_with_scenario(scen)
    img = Image.new("RGB", (64, 64), (1, 2, 3))
    out = up.upscale(img, "4x-UltraSharp.pth")
    assert isinstance(out, Image.Image)
    assert out.size == (256, 256)
    assert len(scen.upload_calls) == 1
    assert len(scen.prompt_calls) == 1
    assert len(scen.view_calls) == 1


def test_upscale_polls_until_outputs_present():
    scen = _ComfyUIScenario([
        {"test-prompt-1": {}},                # 第 1 次空
        {"test-prompt-1": {}},                # 第 2 次空
        _outputs_ready(),                     # 第 3 次有 outputs
    ])
    up = _make_upscaler_with_scenario(scen)
    img = Image.new("RGB", (64, 64))
    up.upscale(img, "4x-UltraSharp.pth")
    assert scen.history_calls == 3


def test_upscale_timeout_raises_upscale_error():
    # history 始终为空 → 超过 timeout 抛错
    scen = _ComfyUIScenario([{"test-prompt-1": {}}])
    up = _make_upscaler_with_scenario(scen, timeout=1)
    img = Image.new("RGB", (64, 64))
    with pytest.raises(ComfyUIUpscaleError) as exc_info:
        up.upscale(img, "4x-UltraSharp.pth")
    assert "timeout" in str(exc_info.value).lower()


def test_upscale_model_not_found_in_prompt_response():
    def handler(req):
        if req.url.path == "/upload/image":
            return httpx.Response(200, json={
                "name": "spb_uploaded.png", "subfolder": "", "type": "input"})
        if req.url.path == "/prompt":
            return httpx.Response(400, json={
                "error": {"message": "Value not in list: model_name: 'wrong.pth'"},
                "node_errors": {}})
        return httpx.Response(404)

    up = ComfyUIUpscaler("http://test:8188")
    up._client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ComfyUIUpscaleError) as exc_info:
        up.upscale(Image.new("RGB", (64, 64)), "wrong.pth")
    assert "model" in str(exc_info.value).lower() or "400" in str(exc_info.value)


def test_upscale_uses_unique_filename_per_call():
    seen = []

    def handler(req):
        if req.url.path == "/upload/image":
            body = req.read().decode("latin-1", errors="ignore")
            m = re.search(r'filename="([^"]+)"', body)
            if m:
                seen.append(m.group(1))
            else:
                pytest.fail("filename not found in multipart body")
            return httpx.Response(200, json={
                "name": seen[-1], "subfolder": "", "type": "input"})
        if req.url.path == "/prompt":
            return httpx.Response(200, json={"prompt_id": "p"})
        if req.url.path.startswith("/history/"):
            return httpx.Response(200, json={
                "p": {"outputs": {
                    "4": {"images": [{"filename": "out.png",
                                       "subfolder": "", "type": "output"}]}}}})
        if req.url.path == "/view":
            return httpx.Response(200, content=_png_bytes(),
                                   headers={"Content-Type": "image/png"})
        return httpx.Response(404)

    up = ComfyUIUpscaler("http://test:8188")
    up._client = httpx.Client(transport=httpx.MockTransport(handler))
    img = Image.new("RGB", (32, 32))
    up.upscale(img, "m.pth")
    up.upscale(img, "m.pth")
    assert len(seen) == 2
    assert seen[0] != seen[1]
