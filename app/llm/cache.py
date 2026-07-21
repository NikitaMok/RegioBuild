"""In-memory LRU-кэш ответов LLM (без Redis — один процесс API на Bothost)."""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict

from loguru import logger

from app.llm.base import DEFAULT_MAX_TOKENS, LLMProvider


class _LRUCache:
    def __init__(self, maxsize: int = 256) -> None:
        self._maxsize = maxsize
        self._data: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> str | None:
        with self._lock:
            value = self._data.get(key)
            if value is None:
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)


def _cache_key(
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    raw = f"{system_prompt}\n---\n{user_prompt}\n---\n{temperature}\n{max_tokens}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class CachingLLMProvider(LLMProvider):
    """Декоратор над LLMProvider с LRU-кэшем полных ответов."""

    def __init__(self, inner: LLMProvider, maxsize: int = 256) -> None:
        self._inner = inner
        self.name = f"cached:{inner.name}"
        self._cache = _LRUCache(maxsize=maxsize)

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> str:
        key = _cache_key(system_prompt, user_prompt, temperature, max_tokens)
        cached = self._cache.get(key)
        if cached is not None:
            logger.info(
                f"LLM cache hit (hits={self._cache.hits}, misses={self._cache.misses})"
            )
            return cached

        result = self._inner.complete(
            system_prompt,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        self._cache.set(key, result)
        return result

    @property
    def cache_stats(self) -> dict[str, int]:
        return {"hits": self._cache.hits, "misses": self._cache.misses}
