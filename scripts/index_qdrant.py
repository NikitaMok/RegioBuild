"""Индексация structured chunks + curated → Qdrant.

Индексатор и runtime API должны использовать один embedding backend
(на Bothost — fastembed). Иначе retrieval деградирует.

Запуск (Qdrant Cloud или локальный):
  set VECTOR_BACKEND=qdrant
  set EMBEDDING_BACKEND=fastembed
  python -m scripts.index_qdrant                # полная переиндексация (reset)
  python -m scripts.index_qdrant --no-reset     # добавление без удаления коллекции
  python -m scripts.index_qdrant --curated-only # только curated-чанки, upsert без reset
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from loguru import logger

from app.core.config import get_settings
from app.core.regions import FEDERAL_CODE, resolve_region_code
from app.embeddings.embedder import Embedder, resolve_embedding_backend, resolve_embedding_model_name
from app.vectorstore.qdrant_store import QdrantStore

BASE_DIR = Path(__file__).resolve().parent.parent
CHUNKS_DIR = BASE_DIR / "data" / "structured" / "chunks"
CURATED_DIR = BASE_DIR / "data" / "curated"


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


def _load_curated_chunks() -> list[dict]:
    """curated JSONL → формат structured chunk (region legacy-алиасы → ISO)."""
    rows: list[dict] = []
    if not CURATED_DIR.exists():
        return rows
    for path in sorted(CURATED_DIR.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                region_iso = resolve_region_code(raw["region_code"])
                section = str(raw.get("section_number") or "").strip()
                body = str(raw.get("text") or "").strip()
                # номер пункта в тексте — для dense/BM25, без keyword-stuffing под queries
                indexed_text = f"{section}. {body}" if section and not body.startswith(section) else body
                rows.append(
                    {
                        "chunk_id": f"curated::{region_iso}::{section}",
                        "text": indexed_text,
                        "region_iso": region_iso,
                        "regulatory_level": "federal" if region_iso == FEDERAL_CODE else "regional",
                        "doc_type": "CURATED",
                        "doc_name": raw.get("source_label") or "curated",
                        "doc_version": "",
                        "clause_number": section,
                        "category": raw.get("category") or "",
                        "is_active": True,
                        "tags": list(raw.get("business_types") or []),
                    }
                )
    return rows


def run(*, reset: bool = True, batch_size: int = 64, curated_only: bool = False) -> int:
    settings = get_settings()
    if curated_only:
        chunks = _load_curated_chunks()
        reset = False
        if not chunks:
            logger.error(f"нет curated-чанков в {CURATED_DIR}")
            return 1
    else:
        chunks = _load_all_chunks()
        if not chunks:
            logger.error(f"нет чанков в {CHUNKS_DIR} — сначала python -m scripts.parse_pdf_docs")
            return 1
        curated = _load_curated_chunks()
        logger.info(f"curated-чанков к индексации: {len(curated)}")
        chunks.extend(curated)

    backend = resolve_embedding_backend()
    model_name = resolve_embedding_model_name()
    logger.info(
        f"чанков к индексации: {len(chunks)}; profile={settings.deploy_profile}; "
        f"backend={backend}; model={model_name}"
    )
    embedder = Embedder(model_name=model_name, backend=backend)
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
                    "category": c.get("category") or "",
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
    curated_only = "--curated-only" in sys.argv
    raise SystemExit(run(reset=reset, curated_only=curated_only))


if __name__ == "__main__":
    main()
