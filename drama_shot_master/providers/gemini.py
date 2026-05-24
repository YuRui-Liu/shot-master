"""Google Gemini vision provider (google-genai SDK).

Runtime dependency: google-genai  (pip install google-genai)
The import is deferred so that the module can be loaded even when the package
is absent – an ImportError is only raised the first time generate() is called.
"""
from __future__ import annotations

from pathlib import Path

try:
    from google import genai  # type: ignore
except ImportError:  # pragma: no cover
    genai = None  # type: ignore

from drama_shot_master.providers.base import VisionProvider, mime_from_suffix


class GeminiProvider(VisionProvider):
    def generate(self,
                 images: list[Path],
                 system_prompt: str,
                 user_supplement: str) -> str:
        if genai is None:  # pragma: no cover
            raise ImportError(
                "google-genai is not installed. Run: pip install google-genai"
            )

        client = genai.Client(api_key=self.config.api_key)

        parts: list = []
        if user_supplement:
            parts.append(user_supplement)
        for img in images:
            mime = mime_from_suffix(img)
            # Access types via genai.types so that the whole module is mockable
            # in tests with a single `patch("drama_shot_master.providers.gemini.genai")`.
            parts.append(genai.types.Part.from_bytes(
                data=img.read_bytes(),
                mime_type=mime,
            ))

        resp = client.models.generate_content(
            model=self.config.model,
            contents=parts,
            config=genai.types.GenerateContentConfig(
                system_instruction=system_prompt,
            ),
        )
        return resp.text or ""

    @classmethod
    def available_models(cls) -> list[str]:
        return [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-3-pro-preview",
        ]
