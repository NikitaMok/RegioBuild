from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
from loguru import logger

from app.core.config import get_settings

# запасной лёгкий вариант, если основная модель не грузится
_FALLBACK_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder:
    def __init__(self, model_name: str | None = None) -> None:
        # sentence_transformers/torch тяжёлые — импорт только здесь, не при старте uvicorn
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        primary = model_name or settings.embedding_model_name
        try:
            self._model: Any = SentenceTransformer(primary)
            self.model_name = primary
        except Exception as exc:
            if primary == _FALLBACK_EMBEDDING_MODEL:
                raise
            logger.warning(
                f"не удалось загрузить embedding «{primary}»: {exc}; "
                f"fallback → {_FALLBACK_EMBEDDING_MODEL}"
            )
            self._model = SentenceTransformer(_FALLBACK_EMBEDDING_MODEL)
            self.model_name = _FALLBACK_EMBEDDING_MODEL

    def encode(self, texts: list[str], batch_size: int = 32, show_progress: bool = False) -> np.ndarray:
        return self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

    def _is_e5(self) -> bool:
        return "e5" in (self.model_name or "").lower()

    def encode_passages(self, texts: list[str], batch_size: int = 32, show_progress: bool = False) -> np.ndarray:
        if self._is_e5():
            texts = [f"passage: {t}" for t in texts]
        return self.encode(texts, batch_size=batch_size, show_progress=show_progress)

    def encode_query(self, text: str) -> np.ndarray:
        if self._is_e5():
            text = f"query: {text}"
        return self.encode([text])[0]

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode_query(text)


@lru_cache
def get_embedder() -> Embedder:
    settings = get_settings()
    model = settings.embedding_model_name
    if settings.deploy_profile == "enterprise":
        model = settings.embedding_model_enterprise
    return Embedder(model_name=model)
