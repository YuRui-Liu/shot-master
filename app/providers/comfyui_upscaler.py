"""ComfyUI HTTP API 客户端：upscale 模型探测 + 上采样工作流提交。

独立于 vision providers——vision 是文本生成、upscale 是图像生成，本质不同路径。
"""
from __future__ import annotations

import httpx


class ComfyUIUnavailable(Exception):
    """ComfyUI 不可达 / 探测失败。调用方应回退 LANCZOS。"""


class ComfyUIUpscaleError(Exception):
    """工作流执行失败（model_not_found / timeout / bad_response）。回退 LANCZOS。"""


class ComfyUIUpscaler:
    def __init__(self, base_url: str, timeout: int = 120):
        """
        Args:
            base_url: ComfyUI 根 URL，如 http://127.0.0.1:8188
            timeout: history 轮询的整体上限秒数；单次 HTTP 请求超时按 10s。
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=10.0)

    def list_models(self) -> list[str]:
        """GET /object_info/UpscaleModelLoader → upscale_model_name 选项列表。

        连接/解析失败抛 ComfyUIUnavailable；JSON 缺节点返回 []。
        """
        url = f"{self.base_url}/object_info/UpscaleModelLoader"
        try:
            resp = self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ComfyUIUnavailable(f"GET {url} 失败: {e}") from e

        try:
            return list(data["UpscaleModelLoader"]["input"]["required"]["model_name"][0])
        except (KeyError, TypeError, IndexError):
            return []
