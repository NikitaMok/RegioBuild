from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np

from app.core.config import get_settings


class Embedder:
    def __init__(self, model_name: str | None = None) -> None:
        # sentence_transformers/torch тяжёлые — импорт только здесь, не при старте uvicorn
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        self.model_name = model_name or settings.embedding_model_name
        self._model: Any = SentenceTransformer(self.model_name)

    def encode(self, texts: list[str], batch_size: int = 32, show_progress: bool = False) -> np.ndarray:
        return self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


@lru_cache
def get_embedder() -> Embedder:
    return Embedder()
