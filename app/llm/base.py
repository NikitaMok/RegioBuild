from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Общий интерфейс для GigaChat/YandexGPT, чтобы агент не зависел от конкретного вендора."""

    name: str = "base"

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        raise NotImplementedError


class LLMProviderError(RuntimeError):
    """Сеть, авторизация, лимиты — всё, что может пойти не так при вызове LLM API."""
