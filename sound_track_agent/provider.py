"""配乐 agent 的 vision provider 构造（参照 prompt_refiner.build_refine_provider）。

默认豆包 doubao-seed-2-0-lite-260215（便宜），OpenAI 兼容接口。
情绪/prompt 的实际调用走 VisionProvider.generate(images, system_prompt, user_supplement)。
"""
from __future__ import annotations

DEFAULT_MODEL = "doubao-seed-2-0-lite-260215"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
REQUEST_TIMEOUT = 300.0      # 多图 + 长输出，放宽超时（同 refine）


def build_soundtrack_provider(cfg):
    """用配乐专属/豆包/refine 配置构造 vision provider。

    取值优先级：cfg.soundtrack_* → cfg.refine_* → cfg.base_urls/api_keys['doubao'] → 默认。
    """
    from drama_shot_master.providers.openai_compat import OpenAICompatProvider
    from drama_shot_master.providers.base import ProviderConfig

    api_key = (getattr(cfg, "soundtrack_api_key", "")
               or getattr(cfg, "refine_api_key", "")
               or getattr(cfg, "api_keys", {}).get("doubao", ""))
    base_url = (getattr(cfg, "soundtrack_base_url", "")
                or getattr(cfg, "refine_base_url", "")
                or getattr(cfg, "base_urls", {}).get("doubao", "")
                or DEFAULT_BASE_URL)
    model = (getattr(cfg, "soundtrack_model", "")
             or getattr(cfg, "refine_model", "")
             or DEFAULT_MODEL)

    return OpenAICompatProvider(ProviderConfig(
        api_key=api_key or "x",
        base_url=base_url,
        model=model,
        timeout=REQUEST_TIMEOUT,
    ))
