from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMProvider
from app.llm.cache import CachingLLMProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()

    if settings.llm_provider == "gigachat":
        from app.llm.gigachat_provider import GigaChatProvider

        inner: LLMProvider = GigaChatProvider()
    elif settings.llm_provider == "yandexgpt":
        from app.llm.yandexgpt_provider import YandexGPTProvider

        inner = YandexGPTProvider()
    else:
        raise ValueError(f"неизвестный LLM_PROVIDER: {settings.llm_provider!r}")

    if settings.llm_cache_enabled:
        return CachingLLMProvider(inner, maxsize=settings.llm_cache_size)
    return inner
