"""Auto-register all providers on import."""
from app.providers import factory
from app.providers.openai_compat import OpenAICompatProvider

factory.register("openai_compat", OpenAICompatProvider)
