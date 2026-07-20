from __future__ import annotations

import pytest

from app.llm.base import LLMProvider, LLMProviderError
from app.llm.fallback import FallbackLLMProvider


class _OkProvider(LLMProvider):
    name = "ok"

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 2500) -> str:
        return "ok-answer"


class _FailProvider(LLMProvider):
    name = "fail"

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 2500) -> str:
        raise LLMProviderError("quota exceeded")


def test_fallback_uses_primary_when_it_works() -> None:
    provider = FallbackLLMProvider(_OkProvider(), _FailProvider())
    assert provider.complete("sys", "user") == "ok-answer"


def test_fallback_switches_to_secondary_on_primary_error() -> None:
    provider = FallbackLLMProvider(_FailProvider(), _OkProvider())
    assert provider.complete("sys", "user") == "ok-answer"


def test_fallback_raises_when_both_fail() -> None:
    provider = FallbackLLMProvider(_FailProvider(), _FailProvider())
    with pytest.raises(LLMProviderError, match="quota exceeded"):
        provider.complete("sys", "user")
