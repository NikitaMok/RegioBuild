"""Загрузка манифеста PDF из config/documents.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DOCUMENTS_YAML = BASE_DIR / "config" / "documents.yaml"
RAW_DOCS_DIR = BASE_DIR / "data" / "raw" / "docs"


@dataclass(frozen=True)
class DocumentSpec:
    id: str
    filename: str
    region_iso: str
    regulatory_level: str
    doc_type: str
    doc_name: str
    doc_version: str
    is_active: bool
    ingest: bool
    scope: str = ""

    @property
    def path(self) -> Path:
        return RAW_DOCS_DIR / self.filename


@lru_cache
def _load_documents() -> tuple[DocumentSpec, ...]:
    with DOCUMENTS_YAML.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    items: list[DocumentSpec] = []
    for row in raw.get("documents") or []:
        items.append(
            DocumentSpec(
                id=str(row["id"]).strip(),
                filename=str(row["filename"]).strip(),
                region_iso=str(row["region_iso"]).strip(),
                regulatory_level=str(row["regulatory_level"]).strip(),
                doc_type=str(row["doc_type"]).strip(),
                doc_name=str(row["doc_name"]).strip(),
                doc_version=str(row.get("doc_version") or "").strip(),
                is_active=bool(row.get("is_active", True)),
                ingest=bool(row.get("ingest", False)),
                scope=str(row.get("scope") or "").strip(),
            )
        )
    return tuple(items)


def all_document_specs() -> tuple[DocumentSpec, ...]:
    return _load_documents()


def ingestible_documents() -> tuple[DocumentSpec, ...]:
    return tuple(d for d in _load_documents() if d.ingest and d.is_active)


def reload_documents() -> None:
    _load_documents.cache_clear()
