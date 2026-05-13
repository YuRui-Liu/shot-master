"""Auto-register all providers on import."""
from app.providers import factory
from app.providers.openai_compat import OpenAICompatProvider
from app.providers.gemini import GeminiProvider

factory.register("openai_compat", OpenAICompatProvider)
factory.register("gemini", GeminiProvider)
