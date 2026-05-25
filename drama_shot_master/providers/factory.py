"""Provider 注册表 + OpenAI 兼容 endpoint 预设。

加新厂商：
- 完全新 SDK → 新建 provider 文件，调 factory.register("name", Cls)
- OpenAI 兼容（base_url + key 即可调） → 直接往 openai_compat_presets 里加一行
"""
from __future__ import annotations

from typing import Type

from drama_shot_master.config import Config
from drama_shot_master.providers.base import VisionProvider, ProviderConfig


_REGISTRY: dict[str, Type[VisionProvider]] = {}


def register(name: str, cls: Type[VisionProvider]) -> None:
    _REGISTRY[name] = cls


def get_provider_class(name: str) -> Type[VisionProvider]:
    if name not in _REGISTRY:
        raise KeyError(name)
    return _REGISTRY[name]


def list_providers() -> list[str]:
    return sorted(_REGISTRY.keys())


def openai_compat_presets() -> dict[str, dict]:
    """OpenAI 兼容 endpoints 的预设。UI 里 'OpenAI 兼容' 选完后，
    具体 endpoint 用这里的 key 名（小写）选。"""
    return {
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
        },
        "deepseek": {
            "base_url": "https://api.deepseek.com/v1",
            "models": ["deepseek-vl2", "deepseek-chat"],
        },
        "doubao": {
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "models": [
                "doubao-seed-2-0-pro-260215",
                "doubao-seed-1-6-vision-250815",
                "doubao-1-5-vision-pro-32k-250115",
                "doubao-1-5-vision-pro-32k",
                "doubao-vision-pro-32k",
            ],
        },
        "openrouter": {
            "base_url": "https://openrouter.ai/api/v1",
            "models": [
                "google/gemini-2.5-pro",
                "anthropic/claude-opus-4",
                "openai/gpt-4o",
            ],
        },
        "siliconflow": {
            "base_url": "https://api.siliconflow.cn/v1",
            "models": ["Qwen/Qwen2.5-VL-72B-Instruct"],
        },
        "vllm": {
            "base_url": "http://127.0.0.1:8000/v1",
            "models": [],
        },
        "ollama": {
            "base_url": "http://localhost:11434/v1",
            "models": ["qwen2.5-vl", "qwen2.5-vl:7b", "qwen2.5-vl:32b"],
        },
    }


def build_provider(cfg: Config,
                   provider_name: str,
                   model: str) -> VisionProvider:
    """从 Config 装配指定 provider。

    provider_name:
      - "gemini" / "anthropic" / "qwen" → 走独立 provider 类
      - "openai" / "deepseek" / "doubao" / "openrouter" / "siliconflow" / "vllm"
        → 全部走 openai_compat 类，但 endpoint 信息从预设拿
    """
    if provider_name in openai_compat_presets():
        cls = get_provider_class("openai_compat")
        preset = openai_compat_presets()[provider_name]
        base_url = cfg.base_urls.get(provider_name) or preset["base_url"]
        api_key = cfg.api_keys.get(provider_name)
        if not api_key:
            raise ValueError(f"missing API key for {provider_name}")
        return cls(ProviderConfig(api_key=api_key, base_url=base_url, model=model))

    cls = get_provider_class(provider_name)
    api_key = cfg.api_keys.get(provider_name)
    if not api_key:
        raise ValueError(f"missing API key for {provider_name}")
    base_url = cfg.base_urls.get(provider_name, "")
    return cls(ProviderConfig(api_key=api_key, base_url=base_url, model=model))
