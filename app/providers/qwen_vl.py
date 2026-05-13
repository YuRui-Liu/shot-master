"""阿里 Qwen-VL via DashScope SDK。"""
from __future__ import annotations

from pathlib import Path

try:
    from dashscope import MultiModalConversation
except ImportError:
    MultiModalConversation = None  # type: ignore[assignment]

from app.providers.base import VisionProvider


class QwenVLProvider(VisionProvider):
    def generate(self,
                 images: list[Path],
                 system_prompt: str,
                 user_supplement: str) -> str:
        if MultiModalConversation is None:
            raise ImportError("dashscope SDK not installed")
        user_content: list[dict] = []
        for img in images:
            user_content.append({"image": str(img.absolute())})
        if user_supplement:
            user_content.append({"text": user_supplement})

        resp = MultiModalConversation.call(
            api_key=self.config.api_key,
            model=self.config.model,
            messages=[
                {"role": "system", "content": [{"text": system_prompt}]},
                {"role": "user", "content": user_content},
            ],
        )
        if getattr(resp, "status_code", 0) != 200:
            raise RuntimeError(f"DashScope error: {getattr(resp, 'message', resp)}")

        parts: list[str] = []
        for item in resp.output.choices[0].message.content:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
        return "".join(parts)

    @classmethod
    def available_models(cls) -> list[str]:
        return [
            "qwen-vl-max-latest",
            "qwen-vl-plus-latest",
            "qwen3-vl-235b-a22b-instruct",
        ]
