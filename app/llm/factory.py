from __future__ import annotations

from functools import lru_cache

from app.core.config import get_settings
from app.llm.base import LLMProvider


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()

    if settings.llm_provider == "gigachat":
        from app.llm.gigachat_provider import GigaChatProvider
        return GigaChatProvider()

    if settings.llm_provider == "yandexgpt":
        from app.llm.yandexgpt_provider import YandexGPTProvider
        return YandexGPTProvider()

    raise ValueError(f"неизвестный LLM_PROVIDER: {settings.llm_provider!r}")
