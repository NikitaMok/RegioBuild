"""Запись curated-чанков в SQLite + Chroma.

Запуск: python -m scripts.ingest_curated

Кураторские тексты имеют приоритет над сырым корпусом с тем же
region_code + section_number: при расхождении текста старые векторы
удаляются и заменяются (иначе «автомойка» КК остаётся на пустой табл. 108).
"""

from __future__ import annotations

import uuid

from loguru import logger
from sqlalchemy import select

from app.db.models import Base, Chunk as ChunkRow, Document as DocumentRow
from app.db.session import engine, get_session
from app.embeddings.embedder import get_embedder
from app.ingestion.federal_sources import all_curated_chunks, write_curated_jsonl


def _needs_replace(existing_docs: list[str], curated_text: str) -> bool:
    """True, если в индексе нет эквивалентного curated-текста."""
    target = (curated_text or "").strip()
    if not target:
        return False
    for doc in existing_docs:
        if (doc or "").strip() == target:
            return False
    return True


def main() -> None:
    Base.metadata.create_all(bind=engine)
    jsonl_path = write_curated_jsonl()
    logger.info(f"curated JSONL: {jsonl_path}")

    try:
        from app.vectorstore.chroma_store import get_chroma_store

        store = get_chroma_store()
    except ModuleNotFoundError:
        logger.warning(
            "chromadb не установлен — curated только в JSONL; "
            "векторный upsert пропущен (контур Qdrant)"
        )
        return

    chunks = all_curated_chunks()
    embedder = get_embedder()

    to_add = []
    replaced = 0
    skipped = 0

    for curated in chunks:
        existing_ids, existing_docs = store.get_section(
            curated.region_code, curated.section_number
        )
        if existing_ids and not _needs_replace(existing_docs, curated.text):
            skipped += 1
            continue
        if existing_ids:
            store.delete_ids(existing_ids)
            replaced += 1
            with get_session() as session:
                rows = session.scalars(
                    select(ChunkRow).where(
                        ChunkRow.region_code == curated.region_code,
                        ChunkRow.section_number == curated.section_number,
                    )
                ).all()
                for row in rows:
                    session.delete(row)
        to_add.append(curated)

    if not to_add:
        logger.info(
            f"ingest_curated: все {len(chunks)} чанков уже актуальны, "
            f"chroma={store.count()}"
        )
        return

    with get_session() as session:
        docs_by_label: dict[str, DocumentRow] = {}
        ids: list[str] = []
        texts: list[str] = []
        metadatas: list[dict] = []

        for curated in to_add:
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
                    "business_types": ",".join(curated.business_types),
                }
            )

        embeddings = embedder.encode(texts)
        store.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=texts,
            metadatas=metadatas,
        )

    logger.info(
        f"ingest_curated: добавлено/обновлено {len(to_add)} "
        f"(заменено {replaced}, без изменений {skipped}), chroma={store.count()}"
    )


if __name__ == "__main__":
    main()
