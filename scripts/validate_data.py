"""Проверка целостности JSONL/кураторских чанков НПА.

Запуск: python -m scripts.validate_data
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.core.regions import all_documents
from app.ingestion.federal_sources import all_curated_chunks

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
CURATED_DIR = BASE_DIR / "data" / "curated"

REQUIRED_FIELDS = ("region_code", "text")


def _validate_jsonl(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"файл отсутствует: {path}"]
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"{path.name}:{line_no}: JSON error: {exc}")
                continue
            for field in REQUIRED_FIELDS:
                if not row.get(field):
                    errors.append(f"{path.name}:{line_no}: пустое поле {field}")
            if not (row.get("section_number") or "").strip():
                errors.append(f"{path.name}:{line_no}: нет section_number")
    return errors


def _validate_source_urls() -> list[str]:
    errors: list[str] = []
    for code, doc in all_documents().items():
        url = (doc.source_url or "").strip()
        # PDF-корпус в data/raw/docs — URL может быть справочным; пустой запрещён в CI
        if not url.startswith(("http://", "https://")):
            errors.append(f"{code}: некорректный source_url")
        if not doc.document_title.strip():
            errors.append(f"{code}: пустой document_title")
        if not doc.last_verified:
            errors.append(f"{code}: нет last_verified")
    return errors


def _validate_processed_jsonl() -> list[str]:
    """Legacy HTML processed/ — только если файлы есть локально; на CI обычно пусто."""
    errors: list[str] = []
    for path in sorted(PROCESSED_DIR.glob("*.jsonl")):
        # не валим CI из-за устаревшего HTML-пайплайна: мягкая проверка
        file_errors = _validate_jsonl(path)
        # ограничиваем шум: максимум 5 сообщений на файл
        errors.extend(file_errors[:5])
        if len(file_errors) > 5:
            errors.append(f"{path.name}: ещё {len(file_errors) - 5} проблем (legacy processed)")
    return errors


def _validate_curated() -> list[str]:
    errors: list[str] = []
    chunks = all_curated_chunks()
    if len(chunks) < 5:
        errors.append("кураторских чанков слишком мало")
    for chunk in chunks:
        if not chunk.text or len(chunk.text) < 40:
            errors.append(f"слишком короткий curated chunk {chunk.section_number}")
        if not chunk.section_number:
            errors.append("curated chunk без section_number")
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_validate_source_urls())
    errors.extend(_validate_curated())

    # legacy processed JSONL не блокирует CI (корпус теперь PDF → structured)
    legacy = _validate_processed_jsonl()
    if legacy:
        print(f"validate_data: legacy processed warnings ({len(legacy)})")
        for err in legacy[:10]:
            print(f"  ~ {err}")

    for path in sorted(CURATED_DIR.glob("*.jsonl")):
        errors.extend(_validate_jsonl(path))

    if errors:
        print(f"validate_data: FAIL ({len(errors)} issues)")
        for err in errors[:50]:
            print(f"  - {err}")
        if len(errors) > 50:
            print(f"  ... и ещё {len(errors) - 50}")
        return 1

    print("validate_data: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
