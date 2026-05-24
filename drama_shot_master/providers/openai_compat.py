"""OpenAI 兼容 vision provider。覆盖 OpenAI / DeepSeek / 豆包 / OpenRouter / vLLM 等。"""
from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from drama_shot_master.providers.base import VisionProvider, encode_image_b64, mime_from_suffix


class OpenAICompatProvider(VisionProvider):
    def generate(self,
                 images: list[Path],
                 system_prompt: str,
                 user_supplement: str) -> str:
        client = OpenAI(api_key=self.config.api_key, base_url=self.config.base_url)
        content: list[dict] = []
        if user_supplement:
            content.append({"type": "text", "text": user_supplement})
        for img in images:
            mime = mime_from_suffix(img)
            b64 = encode_image_b64(img)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}"},
            })
        resp = client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            timeout=self.config.timeout,
        )
        return resp.choices[0].message.content or ""

    @classmethod
    def available_models(cls) -> list[str]:
        # 由 factory.openai_compat_presets() 提供，每个 endpoint 自己一套
        return []
