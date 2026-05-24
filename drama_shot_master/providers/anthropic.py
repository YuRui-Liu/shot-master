"""Anthropic Claude vision provider."""
from __future__ import annotations

from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover
    Anthropic = None  # type: ignore[assignment]

from drama_shot_master.providers.base import VisionProvider, encode_image_b64, mime_from_suffix


class AnthropicProvider(VisionProvider):
    def generate(self,
                 images: list[Path],
                 system_prompt: str,
                 user_supplement: str) -> str:
        if Anthropic is None:  # pragma: no cover
            raise ImportError("anthropic SDK not installed. Run: pip install anthropic")
        client = Anthropic(api_key=self.config.api_key)
        content: list[dict] = []
        if user_supplement:
            content.append({"type": "text", "text": user_supplement})
        for img in images:
            mime = mime_from_suffix(img)
            b64 = encode_image_b64(img)
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": mime, "data": b64},
            })

        resp = client.messages.create(
            model=self.config.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
            timeout=self.config.timeout,
        )
        # Claude response: content is a list of blocks
        parts = []
        for block in resp.content:
            if hasattr(block, "text"):
                parts.append(block.text)
        return "".join(parts)

    @classmethod
    def available_models(cls) -> list[str]:
        return [
            "claude-opus-4-7",
            "claude-opus-4-6",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        ]
