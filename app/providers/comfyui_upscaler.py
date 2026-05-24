"""ComfyUI HTTP API 客户端：upscale 模型探测 + 上采样工作流提交。

独立于 vision providers——vision 是文本生成、upscale 是图像生成，本质不同路径。
"""
from __future__ import annotations

import io
import time
import uuid

import httpx
from PIL import Image


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

    def upscale(self, image: Image.Image, model_name: str) -> Image.Image:
        """提交 4 节点 upscale workflow → 轮询 history → 下载结果。

        连接失败抛 ComfyUIUnavailable；执行失败抛 ComfyUIUpscaleError。
        """
        uploaded = self._upload(image)
        prompt_id = self._submit(self._build_workflow(uploaded, model_name))
        entry = self._wait(prompt_id)
        try:
            out_info = entry["outputs"]["4"]["images"][0]
        except (KeyError, IndexError, TypeError) as e:
            raise ComfyUIUpscaleError(f"bad_response: outputs 结构异常: {e}") from e
        return self._fetch_image(out_info["filename"],
                                  out_info.get("subfolder", ""),
                                  out_info.get("type", "output"))

    def _upload(self, image: Image.Image) -> str:
        buf = io.BytesIO()
        image.save(buf, "PNG")
        buf.seek(0)
        filename = f"spb_{uuid.uuid4().hex}.png"
        files = {"image": (filename, buf, "image/png")}
        data = {"type": "input", "overwrite": "true"}
        try:
            resp = self._client.post(f"{self.base_url}/upload/image",
                                       files=files, data=data)
            resp.raise_for_status()
            return resp.json()["name"]
        except httpx.HTTPError as e:
            raise ComfyUIUnavailable(f"upload 失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise ComfyUIUpscaleError(f"bad_response upload: {e}") from e

    def _build_workflow(self, uploaded_name: str, model_name: str) -> dict:
        return {
            "1": {"class_type": "LoadImage",
                  "inputs": {"image": uploaded_name}},
            "2": {"class_type": "UpscaleModelLoader",
                  "inputs": {"model_name": model_name}},
            "3": {"class_type": "ImageUpscaleWithModel",
                  "inputs": {"upscale_model": ["2", 0], "image": ["1", 0]}},
            "4": {"class_type": "SaveImage",
                  "inputs": {"filename_prefix": "spb_upscale",
                              "images": ["3", 0]}},
        }

    def _submit(self, workflow: dict) -> str:
        client_id = f"spb-{uuid.uuid4().hex}"
        try:
            resp = self._client.post(f"{self.base_url}/prompt",
                                       json={"prompt": workflow,
                                             "client_id": client_id})
            if resp.status_code >= 400:
                raise ComfyUIUpscaleError(
                    f"model_not_found 或参数错（HTTP {resp.status_code}）: "
                    f"{resp.text[:300]}")
            return resp.json()["prompt_id"]
        except httpx.HTTPError as e:
            raise ComfyUIUnavailable(f"submit 失败: {e}") from e
        except (KeyError, ValueError) as e:
            raise ComfyUIUpscaleError(f"bad_response submit: {e}") from e

    def _wait(self, prompt_id: str) -> dict:
        deadline = time.time() + self.timeout
        url = f"{self.base_url}/history/{prompt_id}"
        while time.time() < deadline:
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                data = resp.json()
                entry = data.get(prompt_id)
                if entry and entry.get("outputs"):
                    return entry
            except httpx.HTTPError as e:
                raise ComfyUIUnavailable(f"history 轮询失败: {e}") from e
            except ValueError as e:
                raise ComfyUIUpscaleError(f"bad_response history: {e}") from e
            time.sleep(0.5)
        raise ComfyUIUpscaleError(f"timeout: history {self.timeout}s 无 outputs")

    def _fetch_image(self, filename: str, subfolder: str, type_: str) -> Image.Image:
        params = {"filename": filename, "subfolder": subfolder, "type": type_}
        try:
            resp = self._client.get(f"{self.base_url}/view", params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ComfyUIUnavailable(f"view 下载失败: {e}") from e
        try:
            return Image.open(io.BytesIO(resp.content))
        except Exception as e:
            raise ComfyUIUpscaleError(f"bad_response view: 解码失败 {e}") from e

    def close(self) -> None:
        """Close the underlying httpx client and release its connection pool."""
        self._client.close()

    def __enter__(self) -> "ComfyUIUpscaler":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
