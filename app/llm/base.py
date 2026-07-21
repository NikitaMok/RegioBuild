from __future__ import annotations

from abc import ABC, abstractmethod

# лимит ответа модели: иначе длинные compare/info обрываются на полуслове
# 5500 — компромисс между полнотой JSON и стоимостью/латентностью GigaChat
DEFAULT_MAX_TOKENS = 5500


class LLMProvider(ABC):
    """GigaChat / YandexGPT за одним интерфейсом."""

    name: str = "base"

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        raise NotImplementedError


class LLMProviderError(RuntimeError):
    """Ошибка вызова LLM API."""
