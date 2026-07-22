"""Индексация structured chunks → Qdrant.

Запуск (нужен поднятый Qdrant):
  docker compose --profile enterprise up -d qdrant
  set VECTOR_BACKEND=qdrant
  python -m scripts.index_qdrant
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from loguru import logger

from app.core.config import get_settings
from app.embeddings.embedder import Embedder
from app.vectorstore.qdrant_store import QdrantStore

BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE_DIR / "data" / "structured" / "chunks"


def _load_all_chunks() -> list[dict]:
    rows: list[dict] = []
    if not CHUNKS_DIR.exists():
        return rows
    for path in sorted(CHUNKS_DIR.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
    return rows


def run(*, reset: bool = True, batch_size: int = 64) -> int:
    settings = get_settings()
    chunks = _load_all_chunks()
    if not chunks:
        logger.error(f"нет чанков в {CHUNKS_DIR} — сначала python -m scripts.parse_pdf_docs")
        return 1

    logger.info(f"чанков к индексации: {len(chunks)}; profile={settings.deploy_profile}")
    model_name = (
        settings.embedding_model_enterprise
        if settings.deploy_profile == "enterprise"
        else settings.embedding_model_name
    )
    embedder = Embedder(model_name=model_name)
    store = QdrantStore()
    if reset:
        store.reset()

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [c["text"] for c in batch]
        vectors = embedder.encode_passages(texts, batch_size=batch_size)
        ids = [c["chunk_id"] for c in batch]
        payloads = []
        for c in batch:
            payloads.append(
                {
                    "text": c["text"],
                    "region_iso": c["region_iso"],
                    "regulatory_level": c["regulatory_level"],
                    "doc_type": c["doc_type"],
                    "doc_name": c["doc_name"],
                    "doc_version": c.get("doc_version") or "",
                    "clause_number": c.get("clause_number") or "",
                    "category": "",
                    "is_active": bool(c.get("is_active", True)),
                    "tags": c.get("tags") or [],
                }
            )
        store.upsert(ids, vectors.tolist(), payloads)
        logger.info(f"upsert {start + len(batch)}/{len(chunks)}")

    logger.info(f"готово: points={store.count()} collection={settings.qdrant_collection}")
    return 0


def main() -> None:
    reset = "--no-reset" not in sys.argv
    raise SystemExit(run(reset=reset))


if __name__ == "__main__":
    main()
