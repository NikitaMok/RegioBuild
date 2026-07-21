from __future__ import annotations

from app.llm.base import LLMProvider
from app.llm.cache import CachingLLMProvider


class _CountingProvider(LLMProvider):
    name = "counting"

    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 100,
    ) -> str:
        self.calls += 1
        return f"answer:{user_prompt}"


def test_caching_provider_returns_cached_response() -> None:
    inner = _CountingProvider()
    cached = CachingLLMProvider(inner, maxsize=8)

    first = cached.complete("sys", "user-1")
    second = cached.complete("sys", "user-1")
    third = cached.complete("sys", "user-2")

    assert first == second == "answer:user-1"
    assert third == "answer:user-2"
    assert inner.calls == 2
    assert cached.cache_stats["hits"] == 1
