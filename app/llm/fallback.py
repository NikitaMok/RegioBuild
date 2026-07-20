from __future__ import annotations

from loguru import logger

from app.llm.base import DEFAULT_MAX_TOKENS, LLMProvider, LLMProviderError


class FallbackLLMProvider(LLMProvider):
    """Основной провайдер; при ошибке — резервный (если задан)."""

    name = "fallback"

    def __init__(self, primary: LLMProvider, secondary: LLMProvider) -> None:
        self.primary = primary
        self.secondary = secondary
        self.name = f"{primary.name}+{secondary.name}"

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        try:
            return self.primary.complete(
                system_prompt,
                user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except LLMProviderError as exc:
            logger.warning(
                f"LLM {self.primary.name} недоступен ({exc}); "
                f"переключаюсь на {self.secondary.name}"
            )
            try:
                return self.secondary.complete(
                    system_prompt,
                    user_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except LLMProviderError as secondary_exc:
                raise LLMProviderError(
                    f"{self.primary.name}: {exc}; {self.secondary.name}: {secondary_exc}"
                ) from secondary_exc
