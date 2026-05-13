"""Vision Provider 抽象接口 + 共用工具。"""
from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ProviderConfig:
    api_key: str
    base_url: str
    model: str
    timeout: float = 60.0


class VisionProvider(ABC):
    """所有 vision 后端的统一接口。

    实现类需要在构造时接受 ProviderConfig。
    """

    def __init__(self, config: ProviderConfig):
        self.config = config

    @abstractmethod
    def generate(self,
                 images: list[Path],
                 system_prompt: str,
                 user_supplement: str) -> str:
        """发送 images 给 vision 模型，返回原始文本输出。"""
        ...

    @classmethod
    @abstractmethod
    def available_models(cls) -> list[str]:
        """该 provider 支持的模型名列表（用于 UI 下拉）。"""
        ...


def encode_image_b64(path: Path) -> str:
    """读图片为 base64 字符串（不含 data URL 前缀）。"""
    return base64.b64encode(path.read_bytes()).decode("ascii")


def mime_from_suffix(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(suffix, "image/png")
