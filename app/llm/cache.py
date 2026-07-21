"""In-memory LRU + дисковый кэш ответов LLM (без Redis — один процесс API на Bothost).

Диск нужен потому, что при каждом Sync/пересоздании контейнера память обнуляется,
а /app/data на Bothost обычно сохраняется между деплоями.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from pathlib import Path

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

    def items(self) -> list[tuple[str, str]]:
        with self._lock:
            return list(self._data.items())

    def load_many(self, pairs: list[tuple[str, str]]) -> None:
        with self._lock:
            for key, value in pairs:
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


def _default_persist_path() -> Path:
    from app.core.config import get_settings

    settings = get_settings()
    configured = (getattr(settings, "llm_cache_persist_path", None) or "").strip()
    if configured:
        return Path(configured)

    db_url = settings.database_url
    # sqlite:////app/data/regiobuild.db → /app/data/llm_cache.json
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "", 1)
        # четыре слэша → абсолютный путь на Linux (/app/...)
        if db_path.startswith("/") or (len(db_path) > 2 and db_path[1] == ":"):
            return Path(db_path).resolve().parent / "llm_cache.json"
        return Path(db_path).resolve().parent / "llm_cache.json"
    return Path("data") / "llm_cache.json"


class CachingLLMProvider(LLMProvider):
    """Декоратор над LLMProvider с LRU-кэшем полных ответов (+ опционально диск)."""

    def __init__(
        self,
        inner: LLMProvider,
        maxsize: int = 256,
        persist_path: Path | None = None,
    ) -> None:
        self._inner = inner
        self.name = f"cached:{inner.name}"
        self._cache = _LRUCache(maxsize=maxsize)
        self._persist_path = persist_path if persist_path is not None else _default_persist_path()
        self._disk_lock = threading.Lock()
        self._load_disk()

    def _load_disk(self) -> None:
        path = self._persist_path
        if not path or not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return
            pairs = [(str(k), str(v)) for k, v in raw.items() if isinstance(v, str)]
            self._cache.load_many(pairs[-self._cache._maxsize :])
            logger.info(f"LLM disk cache loaded: {len(pairs)} entries from {path}")
        except Exception:
            logger.exception(f"не удалось загрузить LLM disk cache: {path}")

    def _save_disk(self) -> None:
        path = self._persist_path
        if not path:
            return
        with self._disk_lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                payload = dict(self._cache.items())
                path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            except Exception:
                logger.exception(f"не удалось сохранить LLM disk cache: {path}")

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
        self._save_disk()
        return result

    @property
    def cache_stats(self) -> dict[str, int]:
        return {"hits": self._cache.hits, "misses": self._cache.misses}
