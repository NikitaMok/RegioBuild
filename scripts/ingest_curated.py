"""Запись curated-чанков в SQLite + Chroma.

Запуск: python -m scripts.ingest_curated
"""

from __future__ import annotations

import uuid

from loguru import logger

from app.db.models import Base, Chunk as ChunkRow, Document as DocumentRow
from app.db.session import engine, get_session
from app.embeddings.embedder import get_embedder
from app.ingestion.federal_sources import all_curated_chunks, write_curated_jsonl
from app.vectorstore.chroma_store import get_chroma_store


def main() -> None:
    Base.metadata.create_all(bind=engine)
    jsonl_path = write_curated_jsonl()
    logger.info(f"curated JSONL: {jsonl_path}")

    chunks = all_curated_chunks()
    embedder = get_embedder()
    store = get_chroma_store()

    with get_session() as session:
        # один служебный документ на источник-метку
        docs_by_label: dict[str, DocumentRow] = {}
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict] = []

        for curated in chunks:
            label = curated.source_label
            if label not in docs_by_label:
                doc = DocumentRow(
                    region_code=curated.region_code,
                    title=label,
                    source_url=f"curated://{label}",
                    local_raw_path=str(jsonl_path),
                )
                session.add(doc)
                session.flush()
                docs_by_label[label] = doc

            chunk_id = str(uuid.uuid4())
            row = ChunkRow(
                id=chunk_id,
                document_id=docs_by_label[label].id,
                region_code=curated.region_code,
                section_number=curated.section_number,
                category=curated.category or None,
                text=curated.text,
                char_count=len(curated.text),
                vector_id=chunk_id,
            )
            session.add(row)
            ids.append(chunk_id)
            texts.append(curated.text)
            metadatas.append(
                {
                    "region_code": curated.region_code,
                    "section_number": curated.section_number,
                    "document_id": docs_by_label[label].id,
                    "category": curated.category or "",
                }
            )

        embeddings = embedder.encode(texts)
        store.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas,
        )

    logger.info(f"ingest_curated: добавлено {len(chunks)} чанков, chroma={store.count()}")


if __name__ == "__main__":
    main()
