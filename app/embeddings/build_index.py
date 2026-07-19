"""Запуск: python -m app.embeddings.build_index

Берёт все чанки из Postgres, считает эмбеддинги и заливает их в Chroma.
"""

from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from app.db.models import Chunk
from app.db.session import get_session
from app.embeddings.embedder import get_embedder
from app.vectorstore.chroma_store import get_chroma_store

BATCH_SIZE = 64


def build_index(reset: bool = True) -> int:
    store = get_chroma_store()
    if reset:
        logger.info("пересобираю коллекцию Chroma с нуля")
        store.reset()

    embedder = get_embedder()
    indexed_count = 0

    with get_session() as session:
        chunks = session.scalars(select(Chunk)).all()
        logger.info(f"чанков в БД: {len(chunks)}")

        for offset in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[offset : offset + BATCH_SIZE]
            texts = [chunk.text for chunk in batch]
            embeddings = embedder.encode(texts)

            store.add(
                ids=[chunk.id for chunk in batch],
                embeddings=embeddings.tolist(),
                documents=texts,
                metadatas=[
                    {
                        "region_code": chunk.region_code,
                        "section_number": chunk.section_number or "",
                        "document_id": chunk.document_id,
                        "category": chunk.category or "",
                    }
                    for chunk in batch
                ],
            )

            for chunk in batch:
                chunk.vector_id = chunk.id

            indexed_count += len(batch)
            logger.info(f"проиндексировано {indexed_count}/{len(chunks)}")

    logger.info(f"готово, всего векторов в коллекции: {store.count()}")
    return indexed_count


if __name__ == "__main__":
    build_index()
