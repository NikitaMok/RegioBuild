"""Локальный реранкер: CrossEncoder при наличии модели, иначе сортировка по distance."""

from __future__ import annotations

import os
from functools import lru_cache

from loguru import logger

from app.vectorstore.types import RetrievedChunk

_DEFAULT_RERANKER = "BAAI/bge-reranker-base"


@lru_cache
def _load_cross_encoder():
    model_name = os.getenv("RERANKER_MODEL", "").strip()
    if not model_name:
        return None
    try:
        from sentence_transformers import CrossEncoder

        logger.info(f"загрузка reranker {model_name}")
        return CrossEncoder(model_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"reranker недоступен ({exc}), использую distance-sort")
        return None


def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    *,
    top_n: int = 3,
) -> list[RetrievedChunk]:
    if not chunks:
        return []
    if len(chunks) <= top_n:
        return list(chunks)

    model = _load_cross_encoder()
    if model is None:
        return sorted(chunks, key=lambda c: c.distance)[:top_n]

    pairs = [(query, c.text) for c in chunks]
    scores = model.predict(pairs)
    ranked = sorted(zip(chunks, scores), key=lambda x: float(x[1]), reverse=True)
    return [c for c, _ in ranked[:top_n]]
