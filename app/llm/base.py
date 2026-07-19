from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """GigaChat / YandexGPT за одним интерфейсом."""

    name: str = "base"

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        raise NotImplementedError


class LLMProviderError(RuntimeError):
    """Ошибка вызова LLM API."""
