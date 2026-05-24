"""Auto-register all providers on import."""
from drama_shot_master.providers import factory
from drama_shot_master.providers.openai_compat import OpenAICompatProvider
from drama_shot_master.providers.gemini import GeminiProvider
from drama_shot_master.providers.anthropic import AnthropicProvider
from drama_shot_master.providers.qwen_vl import QwenVLProvider

factory.register("openai_compat", OpenAICompatProvider)
factory.register("gemini", GeminiProvider)
factory.register("anthropic", AnthropicProvider)
factory.register("qwen", QwenVLProvider)
