"""Запуск: python -m app.ingestion.pipeline

Прогоняет все регионы из REGIONS плюс федеральный СП 42.13330.2016 через
скрапинг -> парсинг -> чанкинг и сохраняет результат и в JSONL (для дебага),
и в Postgres (для дальнейшей индексации).
"""

from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from sqlalchemy import delete, select

from app.core.regions import all_documents
from app.db.models import Base, Chunk as ChunkRow, Document as DocumentRow
from app.db.session import engine, get_session
from app.ingestion.chunker import chunk_sections
from app.ingestion.parser import parse_region_document
from app.ingestion.scraper import FetchError, fetch_region_document

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "processed"


def _save_chunks_as_jsonl(region_code: str, chunks: list) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{region_code}.jsonl"

    with out_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            row = {
                "region_code": chunk.region_code,
                "section_number": chunk.section_number,
                "text": chunk.text,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    return out_path


def _prune_removed_regions(known_codes: set[str]) -> None:
    """Если регион убрали из REGIONS (как Ленинградскую область — источник
    оказался без реального текста норматива), его старые чанки сами по себе
    из БД не денутся и попадут в Chroma при следующей переиндексации. Чистим
    их здесь, а не оставляем как мёртвый груз."""
    with get_session() as session:
        stale_ids = session.scalars(
            select(DocumentRow.id).where(DocumentRow.region_code.not_in(known_codes))
        ).all()
        if not stale_ids:
            return

        stale_codes = session.scalars(
            select(DocumentRow.region_code).where(DocumentRow.id.in_(stale_ids)).distinct()
        ).all()
        session.execute(delete(ChunkRow).where(ChunkRow.document_id.in_(stale_ids)))
        session.execute(delete(DocumentRow).where(DocumentRow.id.in_(stale_ids)))
        logger.info(f"удалены данные регионов, убранных из REGIONS: {stale_codes}")


def run_pipeline(force_download: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    documents = all_documents()
    _prune_removed_regions(set(documents.keys()))

    for region_code, doc in documents.items():
        logger.info(f"=== {doc.display_name} ({region_code}) ===")

        try:
            raw_path = fetch_region_document(doc, force=force_download)
        except FetchError as exc:
            logger.error(str(exc))
            continue

        sections = parse_region_document(raw_path)
        logger.info(f"[{region_code}] разделов найдено: {len(sections)}")

        chunks = chunk_sections(sections, region_code=region_code)
        logger.info(f"[{region_code}] чанков получено: {len(chunks)}")

        processed_path = _save_chunks_as_jsonl(region_code, chunks)
        logger.info(f"[{region_code}] сохранено в {processed_path}")

        with get_session() as session:
            # без этого повторный запуск пайплайна плодил бы дубликаты при каждом
            # перезапуске (например, после смены источника документа для региона)
            old_document_ids = session.scalars(
                select(DocumentRow.id).where(DocumentRow.region_code == region_code)
            ).all()
            if old_document_ids:
                session.execute(delete(ChunkRow).where(ChunkRow.document_id.in_(old_document_ids)))
                session.execute(delete(DocumentRow).where(DocumentRow.id.in_(old_document_ids)))
                logger.info(f"[{region_code}] удалены старые данные ({len(old_document_ids)} документ(ов))")

            document = DocumentRow(
                region_code=region_code,
                title=doc.document_title,
                source_url=doc.source_url,
                local_raw_path=str(raw_path),
            )
            session.add(document)
            session.flush()  # нужно получить document.id перед созданием чанков

            for chunk in chunks:
                session.add(
                    ChunkRow(
                        document_id=document.id,
                        region_code=chunk.region_code,
                        section_number=chunk.section_number,
                        text=chunk.text,
                        char_count=chunk.char_count,
                    )
                )

        logger.info(f"[{region_code}] записано в БД")


if __name__ == "__main__":
    run_pipeline()
