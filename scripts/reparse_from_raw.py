"""Перепарс raw → processed JSONL без обязательной записи в БД.

Запуск:
  python -m scripts.reparse_from_raw
  python -m scripts.reparse_from_raw --with-db

Для Краснодарского края без raw docx — repair табличных section_number
в уже существующем processed JSONL.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from loguru import logger

from app.core.regions import all_documents
from app.ingestion.chunker import chunk_sections
from app.ingestion.parser import parse_region_document

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"

_TABLE_TITLE = re.compile(r"Таблица\s+(\d+)", re.IGNORECASE)
_PIPE = re.compile(r"\s\|\s")


def _save_jsonl(region_code: str, chunks: list) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"{region_code}.jsonl"
    with out_path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(
                json.dumps(
                    {
                        "region_code": chunk.region_code,
                        "section_number": chunk.section_number,
                        "text": chunk.text,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    return out_path


def reparse_region(region_code: str, raw_path: Path) -> int:
    sections = parse_region_document(raw_path)
    chunks = chunk_sections(sections, region_code=region_code)
    path = _save_jsonl(region_code, chunks)
    logger.info(f"[{region_code}] {len(chunks)} чанков → {path}")
    return len(chunks)


def repair_table_sections(region_code: str) -> int:
    """Пост-обработка: строки с «|» под «Таблица N» → section табл.N; сброс junk ≥100."""
    path = PROCESSED_DIR / f"{region_code}.jsonl"
    if not path.exists():
        logger.warning(f"нет файла для repair: {path}")
        return 0

    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    active_table: str | None = None
    changed = 0
    for row in rows:
        text = row.get("text") or ""
        table_match = _TABLE_TITLE.search(text)
        if table_match:
            active_table = f"табл.{table_match.group(1)}"

        section = (row.get("section_number") or "").strip()
        looks_table = bool(_PIPE.search(text) or text.strip().startswith("|"))
        is_junk_small = section in {"1", "2", "3"}
        is_junk_big = section.isdigit() and int(section) >= 100

        if active_table and looks_table and (is_junk_small or is_junk_big or not section):
            row["section_number"] = active_table
            changed += 1
        elif is_junk_big and looks_table and active_table:
            row["section_number"] = active_table
            changed += 1
        elif is_junk_small or is_junk_big:
            # голые «1»/«300» без табличного контекста — не пункты НПА
            row["section_number"] = None
            changed += 1

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    logger.info(f"[{region_code}] repair: изменено {changed} строк")
    return changed


def write_to_db_from_processed() -> None:
    """Перезалить processed JSONL в SQLite (без скачивания raw)."""
    from sqlalchemy import delete, select

    from app.db.models import Base, Chunk as ChunkRow, Document as DocumentRow
    from app.db.session import engine, get_session

    Base.metadata.create_all(bind=engine)
    documents = all_documents()

    for region_code, doc in documents.items():
        path = PROCESSED_DIR / f"{region_code}.jsonl"
        if not path.exists():
            logger.warning(f"пропуск БД {region_code}: нет {path}")
            continue
        rows = []
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))

        with get_session() as session:
            old_ids = session.scalars(
                select(DocumentRow.id).where(DocumentRow.region_code == region_code)
            ).all()
            if old_ids:
                session.execute(delete(ChunkRow).where(ChunkRow.document_id.in_(old_ids)))
                session.execute(delete(DocumentRow).where(DocumentRow.id.in_(old_ids)))

            document = DocumentRow(
                region_code=region_code,
                title=doc.document_title,
                source_url=doc.source_url,
                local_raw_path=str(RAW_DIR / doc.local_raw_filename),
            )
            session.add(document)
            session.flush()
            for row in rows:
                text = row.get("text") or ""
                session.add(
                    ChunkRow(
                        document_id=document.id,
                        region_code=region_code,
                        section_number=row.get("section_number"),
                        text=text,
                        char_count=len(text),
                    )
                )
        logger.info(f"[{region_code}] в БД: {len(rows)} чанков")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-db", action="store_true", help="записать processed в SQLite")
    parser.add_argument(
        "--build-index",
        action="store_true",
        help="пересобрать Chroma из БД и прогнать ingest_curated",
    )
    args = parser.parse_args()

    documents = all_documents()
    for region_code, doc in documents.items():
        raw_path = RAW_DIR / doc.local_raw_filename
        if raw_path.exists():
            reparse_region(region_code, raw_path)
        elif region_code == "krasnodar_krai":
            logger.warning("нет raw для КК — только repair processed")
            repair_table_sections(region_code)
        else:
            logger.warning(f"нет raw для {region_code}: {raw_path}")
            if (PROCESSED_DIR / f"{region_code}.jsonl").exists():
                repair_table_sections(region_code)

    # доп. проход repair по всем (в т.ч. после reparse — harmless для dotted)
    for region_code in documents:
        if (PROCESSED_DIR / f"{region_code}.jsonl").exists():
            repair_table_sections(region_code)

    if args.with_db or args.build_index:
        write_to_db_from_processed()

    if args.build_index:
        from app.embeddings.build_index import build_index
        from scripts.ingest_curated import main as ingest_curated_main

        build_index(reset=True)
        ingest_curated_main()

    return 0


if __name__ == "__main__":
    sys.exit(main())
