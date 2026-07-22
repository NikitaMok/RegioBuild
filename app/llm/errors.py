"""Человекочитаемые сообщения об ошибках LLM (без сырого traceback в UI)."""

from __future__ import annotations

from app.llm.base import LLMProviderError
from app.llm.parsing import LLMParsingError


def friendly_llm_failure(exc: BaseException, *, mode: str = "info") -> str:
    """mode: info | compare — формулировка «справки»."""
    what = "сравнительную справку" if mode == "compare" else "справку"
    text = str(exc)
    lowered = text.lower()

    if isinstance(exc, LLMProviderError) or "gigachat" in lowered or "oauth" in lowered:
        if "401" in text or "credentials" in lowered or "doesn't match" in lowered:
            return (
                "GigaChat отклонил авторизацию (код 401). "
                "Обновите GIGACHAT_CREDENTIALS в .env в кабинете разработчика Сбера "
                "и перезапустите API."
            )
        if "403" in text or "forbidden" in lowered:
            return "GigaChat запретил запрос (403). Проверьте scope/модель и доступ проекта."
        if "429" in text or "quota" in lowered or "rate" in lowered or "limit" in lowered:
            return (
                "GigaChat временно недоступен из‑за лимита/квоты. "
                "Подождите и повторите запрос."
            )
        if "timeout" in lowered or "timed out" in lowered:
            return f"Таймаут при обращении к модели. Не удалось сформировать {what}."
        return f"Сервис генерации временно недоступен. Не удалось сформировать {what}."

    if isinstance(exc, LLMParsingError):
        return (
            f"Не удалось разобрать ответ модели в формат {what}. "
            "Попробуйте ещё раз или укажите объект короче (например: торговый центр)."
        )

    return f"Не удалось сформировать {what}. Попробуйте ещё раз."
