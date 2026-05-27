"""图片生成 provider：抽象 + 豆包(ARK)/OpenAI/RunningHub(占位) + 工厂。"""
from __future__ import annotations

import base64
import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path

import httpx


class ImageGenError(Exception):
    pass


def _to_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    b64 = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


class ImageGenProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str, references: list[Path], *,
                 size: str | None, n: int) -> list[bytes]:
        ...

    def test_connection(self) -> tuple[bool, str]:
        """轻量连通性/鉴权探测，不生成图片。返回 (ok, 说明)。"""
        return (False, "该提供方不支持测试")


class DoubaoImageProvider(ImageGenProvider):
    """火山引擎 ARK images/generations（Seedream）。"""

    def __init__(self, api_key: str, base_url: str, model: str,
                 watermark: bool = False):
        self.api_key = api_key
        self.base_url = (base_url or "https://ark.cn-beijing.volces.com").rstrip("/")
        self.model = model
        self.watermark = watermark

    def _build_payload(self, prompt, references, *, size, n) -> dict:
        body: dict = {"model": self.model, "prompt": prompt, "n": n,
                      "response_format": "b64_json", "watermark": self.watermark}
        if size:
            body["size"] = size
        if references:
            body["image"] = [_to_data_url(p) for p in references]
        return body

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return (False, "未填 API Key")
        try:
            r = httpx.get(self.base_url,
                          headers={"Authorization": f"Bearer {self.api_key}"},
                          timeout=8)
        except httpx.HTTPError as e:
            return (False, f"连不上：{e}")
        if r.status_code in (401, 403):
            return (False, f"鉴权失败(HTTP {r.status_code})，请检查 API Key")
        tail = "" if self.model else "（注意：模型 id 尚未填写）"
        return (True, f"链路正常(HTTP {r.status_code}){tail}")

    def _parse_response(self, data: dict) -> list[bytes]:
        items = data.get("data") or []
        out = []
        for it in items:
            b64 = it.get("b64_json")
            if b64:
                out.append(base64.b64decode(b64))
            elif it.get("url"):
                out.append(httpx.get(it["url"], timeout=60).content)
        if not out:
            raise ImageGenError(f"无图片返回: {str(data)[:300]}")
        return out

    def generate(self, prompt, references, *, size, n) -> list[bytes]:
        if not self.api_key:
            raise ImageGenError("未配置豆包 API Key（设置→图片生成）")
        if not self.model:
            raise ImageGenError("未配置图片模型 id（设置→图片生成）")
        url = f"{self.base_url}/api/v3/images/generations"
        try:
            resp = httpx.post(url, json=self._build_payload(
                prompt, references, size=size, n=n),
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"}, timeout=300)
        except httpx.HTTPError as e:
            raise ImageGenError(f"连接失败: {e}") from e
        if resp.status_code >= 400:
            raise ImageGenError(f"HTTP {resp.status_code}: {resp.text[:400]}")
        return self._parse_response(resp.json())


class OpenAIImageProvider(ImageGenProvider):
    """OpenAI images（无参考图=generations，有参考图=edits）。"""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com").rstrip("/")
        self.model = model or "gpt-image-1"

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return (False, "未填 API Key")
        try:
            r = httpx.get(f"{self.base_url}/v1/models",
                          headers={"Authorization": f"Bearer {self.api_key}"},
                          timeout=8)
        except httpx.HTTPError as e:
            return (False, f"连不上：{e}")
        if r.status_code in (401, 403):
            return (False, f"鉴权失败(HTTP {r.status_code})，请检查 API Key")
        if r.status_code >= 400:
            return (False, f"HTTP {r.status_code}")
        return (True, "链路与鉴权正常")

    def generate(self, prompt, references, *, size, n) -> list[bytes]:
        if not self.api_key:
            raise ImageGenError("未配置 OpenAI API Key（设置→图片生成）")
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            if references:
                files = [("image[]", (Path(p).name, Path(p).read_bytes(),
                          mimetypes.guess_type(str(p))[0] or "image/png"))
                         for p in references]
                data = {"model": self.model, "prompt": prompt, "n": str(n)}
                if size:
                    data["size"] = size
                resp = httpx.post(f"{self.base_url}/v1/images/edits",
                                  data=data, files=files, headers=headers, timeout=300)
            else:
                body = {"model": self.model, "prompt": prompt, "n": n}
                if size:
                    body["size"] = size
                resp = httpx.post(f"{self.base_url}/v1/images/generations",
                                  json=body, headers={**headers,
                                  "Content-Type": "application/json"}, timeout=300)
        except httpx.HTTPError as e:
            raise ImageGenError(f"连接失败: {e}") from e
        if resp.status_code >= 400:
            raise ImageGenError(f"HTTP {resp.status_code}: {resp.text[:400]}")
        out = []
        for it in resp.json().get("data", []):
            if it.get("b64_json"):
                out.append(base64.b64decode(it["b64_json"]))
            elif it.get("url"):
                out.append(httpx.get(it["url"], timeout=60).content)
        if not out:
            raise ImageGenError("无图片返回")
        return out


class RunningHubImageProvider(ImageGenProvider):
    """占位：待提供图片工作流后通过插件接入。"""

    def generate(self, prompt, references, *, size, n) -> list[bytes]:
        raise ImageGenError("RunningHub 图片工作流暂未接入，待提供工作流后通过插件接入")

    def test_connection(self) -> tuple[bool, str]:
        return (False, "RunningHub 图片工作流暂未接入")


def make_image_provider(cfg) -> ImageGenProvider:
    prov = getattr(cfg, "imggen_provider", "doubao")
    # 优先用设置里持久化的 imggen_api_key；为空则回退 .env 的 api_keys[prov]
    key = getattr(cfg, "imggen_api_key", "") or (getattr(cfg, "api_keys", {}) or {}).get(prov, "")
    base = getattr(cfg, "imggen_base_url", "")
    model = getattr(cfg, "imggen_model", "")
    if prov == "openai":
        return OpenAIImageProvider(key, base, model)
    if prov == "runninghub":
        return RunningHubImageProvider()
    return DoubaoImageProvider(key, base, model,
                               watermark=bool(getattr(cfg, "imggen_watermark", False)))
