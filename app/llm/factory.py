from __future__ import annotations

from functools import lru_cache

from loguru import logger

from app.core.config import Settings, get_settings
from app.llm.base import LLMProvider, LLMProviderError


def _has_credentials(provider_name: str, settings: Settings) -> bool:
    if provider_name == "gigachat":
        return bool(settings.gigachat_credentials.strip())
    if provider_name == "yandexgpt":
        return bool(settings.yandex_api_key.strip() and settings.yandex_folder_id.strip())
    return False


def _build_provider(provider_name: str) -> LLMProvider:
    if provider_name == "gigachat":
        from app.llm.gigachat_provider import GigaChatProvider
        return GigaChatProvider()
    if provider_name == "yandexgpt":
        from app.llm.yandexgpt_provider import YandexGPTProvider
        return YandexGPTProvider()
    raise ValueError(f"неизвестный LLM_PROVIDER: {provider_name!r}")


def _other_provider(provider_name: str) -> str:
    return "yandexgpt" if provider_name == "gigachat" else "gigachat"


@lru_cache
def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    primary_name = settings.llm_provider
    primary = _build_provider(primary_name)

    if not settings.llm_fallback_enabled:
        return primary

    fallback_name = _other_provider(primary_name)
    if not _has_credentials(fallback_name, settings):
        logger.info(
            f"резервный LLM ({fallback_name}) не настроен — работаю только через {primary_name}"
        )
        return primary

    try:
        secondary = _build_provider(fallback_name)
    except LLMProviderError as exc:
        logger.warning(f"не удалось создать резервный LLM {fallback_name}: {exc}")
        return primary

    from app.llm.fallback import FallbackLLMProvider

    logger.info(f"LLM: основной {primary_name}, резерв {fallback_name}")
    return FallbackLLMProvider(primary, secondary)
