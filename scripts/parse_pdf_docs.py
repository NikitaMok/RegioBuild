"""PDF → structured JSON + hierarchical chunks.

Запуск: python -m scripts.parse_pdf_docs
Только документы с ingest: true из config/documents.yaml.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from loguru import logger

from app.core.documents import ingestible_documents
from app.ingestion.pdf_parser import build_hierarchical_chunks, parse_pdf_to_structured

BASE_DIR = Path(__file__).resolve().parent.parent
STRUCTURED_DIR = BASE_DIR / "data" / "structured"
CHUNKS_DIR = STRUCTURED_DIR / "chunks"


def run(limit: int | None = None, only_ids: set[str] | None = None) -> int:
    STRUCTURED_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    docs = list(ingestible_documents())
    if only_ids:
        docs = [d for d in docs if d.id in only_ids]
    if limit is not None:
        docs = docs[:limit]

    if not docs:
        logger.error("нет документов с ingest=true")
        return 1

    summary: list[dict] = []
    total_clauses = 0
    total_chunks = 0

    for spec in docs:
        if not spec.path.exists():
            logger.error(f"файл не найден: {spec.path}")
            summary.append({"id": spec.id, "error": "missing_file", "filename": spec.filename})
            continue

        logger.info(f"парсинг {spec.id}: {spec.filename}")
        try:
            structured = parse_pdf_to_structured(
                spec.path,
                doc_id=spec.id,
                doc_name=spec.doc_name,
                region_iso=spec.region_iso,
                regulatory_level=spec.regulatory_level,
                doc_type=spec.doc_type,
                doc_version=spec.doc_version,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"ошибка парсинга {spec.id}: {exc}")
            summary.append({"id": spec.id, "error": str(exc), "filename": spec.filename})
            continue

        out_json = STRUCTURED_DIR / f"{spec.id}.json"
        out_json.write_text(
            json.dumps(structured.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        chunks = build_hierarchical_chunks(structured)
        chunks_path = CHUNKS_DIR / f"{spec.id}.jsonl"
        with chunks_path.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + "\n")

        total_clauses += structured.sections_count
        total_chunks += len(chunks)
        row = {
            "id": spec.id,
            "filename": spec.filename,
            "region_iso": spec.region_iso,
            "clauses": structured.sections_count,
            "tables": structured.tables_count,
            "chunks": len(chunks),
            "structured_path": str(out_json.relative_to(BASE_DIR)),
            "chunks_path": str(chunks_path.relative_to(BASE_DIR)),
        }
        summary.append(row)
        logger.info(
            f"[{spec.id}] clauses={structured.sections_count} "
            f"tables={structured.tables_count} chunks={len(chunks)}"
        )

    summary_path = STRUCTURED_DIR / "_summary.json"
    if only_ids and summary_path.exists():
        try:
            prev = json.loads(summary_path.read_text(encoding="utf-8"))
            by_id = {r["id"]: r for r in prev.get("documents", [])}
            for row in summary:
                by_id[row["id"]] = row
            merged = list(by_id.values())
            summary = merged
            total_clauses = sum(int(r.get("clauses", 0)) for r in merged)
            total_chunks = sum(int(r.get("chunks", 0)) for r in merged)
            ingestible_count = len(merged)
        except Exception:  # noqa: BLE001
            ingestible_count = len(docs)
    else:
        ingestible_count = len(docs)

    summary_path.write_text(
        json.dumps(
            {
                "documents": summary,
                "total_clauses": total_clauses,
                "total_chunks": total_chunks,
                "ingestible": ingestible_count,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(f"итог: clauses={total_clauses} chunks={total_chunks} → {summary_path}")
    return 0 if not any("error" in r for r in summary) else 2


def main() -> None:
    limit = None
    only_ids: set[str] | None = None
    args = sys.argv[1:]
    if args and args[0].isdigit():
        limit = int(args[0])
        args = args[1:]
    if args and args[0] == "--only":
        only_ids = set(args[1:])
    raise SystemExit(run(limit=limit, only_ids=only_ids))


if __name__ == "__main__":
    main()
