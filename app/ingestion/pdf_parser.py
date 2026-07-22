"""Иерархический парсинг PDF НПА → structured clauses + micro-chunks.

Наследование контекста: в текст чанка вклеиваются документ / глава / пункт.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pdfplumber
from loguru import logger

# пункт вида 5.2.3 / 5.2 / 12
_CLAUSE_LINE = re.compile(
    r"^(?:п(?:ункт)?\.?\s*)?(\d{1,3}(?:\.\d{1,3}){0,5})\.?\s+(.+)$",
    re.IGNORECASE,
)
_SUBPOINT = re.compile(r"^([а-яa-z])\)\s+(.+)$", re.IGNORECASE)
_CHAPTER = re.compile(
    r"^(?:глава|раздел|часть)\s+([IVXLC\d]+|[А-ЯA-Z\d\.]+)[\.\s:—-]*(.*)$",
    re.IGNORECASE,
)
_ARTICLE = re.compile(
    r"^(?:статья|ст\.)\s*(\d+(?:\.\d+)*)[\.\s:—-]*(.*)$",
    re.IGNORECASE,
)
_TABLE_TITLE = re.compile(r"таблица\s+(\d+[а-яa-z]?)", re.IGNORECASE)


@dataclass
class Hierarchy:
    chapter: str = ""
    article: str = ""
    paragraph: str = ""
    subpoint: str = ""


@dataclass
class StructuredClause:
    clause_number: str
    text: str
    hierarchy: Hierarchy = field(default_factory=Hierarchy)
    table_text: str = ""
    page: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "clause_number": self.clause_number,
            "text": self.text,
            "hierarchy": asdict(self.hierarchy),
            "table_text": self.table_text,
            "page": self.page,
        }


@dataclass
class StructuredDocument:
    doc_id: str
    doc_name: str
    region_iso: str
    regulatory_level: str
    doc_type: str
    doc_version: str
    clauses: list[StructuredClause] = field(default_factory=list)
    sections_count: int = 0
    tables_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "doc_name": self.doc_name,
            "region_iso": self.region_iso,
            "regulatory_level": self.regulatory_level,
            "doc_type": self.doc_type,
            "doc_version": self.doc_version,
            "sections_count": self.sections_count,
            "tables_count": self.tables_count,
            "clauses": [c.to_dict() for c in self.clauses],
        }


@dataclass
class HierarchicalChunk:
    chunk_id: str
    region_iso: str
    regulatory_level: str
    doc_type: str
    doc_name: str
    doc_version: str
    clause_number: str
    text: str
    hierarchy: Hierarchy
    tags: list[str] = field(default_factory=list)
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "region_iso": self.region_iso,
            "regulatory_level": self.regulatory_level,
            "doc_type": self.doc_type,
            "doc_name": self.doc_name,
            "doc_version": self.doc_version,
            "clause_number": self.clause_number,
            "text": self.text,
            "hierarchy": asdict(self.hierarchy),
            "tags": self.tags,
            "is_active": self.is_active,
        }


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", (line or "").replace("\u00a0", " ")).strip()


def _table_to_text(table: list[list[str | None]] | None) -> str:
    if not table:
        return ""
    rows: list[str] = []
    for row in table:
        cells = [_normalize_line(str(c or "")) for c in row]
        cells = [c for c in cells if c]
        if cells:
            rows.append(" | ".join(cells))
    if not rows:
        return ""
    header = rows[0]
    body = "; ".join(rows[1:]) if len(rows) > 1 else ""
    if body:
        return f"Заголовки: {header}; строки: {body}"
    return f"Заголовки: {header}"


def extract_pdf_lines(path: Path) -> list[tuple[int, str]]:
    """Возвращает (page_number, line) по всему PDF."""
    lines: list[tuple[int, str]] = []
    with pdfplumber.open(str(path)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            for raw in text.splitlines():
                line = _normalize_line(raw)
                if line:
                    lines.append((page_idx, line))
    return lines


def extract_pdf_tables(path: Path) -> list[tuple[int, str]]:
    """Список (page, table_text); ошибки отдельных таблиц пропускаем."""
    tables: list[tuple[int, str]] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                try:
                    for table in page.extract_tables() or []:
                        rendered = _table_to_text(table)
                        if rendered:
                            tables.append((page_idx, rendered))
                except Exception as exc:  # noqa: BLE001 — одна битая таблица не валит документ
                    logger.warning(f"таблица на стр. {page_idx} пропущена: {exc}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"не удалось извлечь таблицы из {path.name}: {exc}")
    return tables


def parse_pdf_to_structured(
    path: Path,
    *,
    doc_id: str,
    doc_name: str,
    region_iso: str,
    regulatory_level: str,
    doc_type: str,
    doc_version: str,
) -> StructuredDocument:
    """Rule-based разбор PDF на clauses с иерархией."""
    lines = extract_pdf_lines(path)
    page_tables = extract_pdf_tables(path)
    tables_by_page: dict[int, list[str]] = {}
    for page, table_text in page_tables:
        tables_by_page.setdefault(page, []).append(table_text)

    hierarchy = Hierarchy()
    clauses: list[StructuredClause] = []
    current: StructuredClause | None = None
    tables_attached = 0

    def flush() -> None:
        nonlocal current
        if current and (current.text.strip() or current.table_text):
            clauses.append(current)
        current = None

    for page, line in lines:
        chapter_m = _CHAPTER.match(line)
        if chapter_m:
            flush()
            hierarchy = Hierarchy(
                chapter=_normalize_line(f"Глава {chapter_m.group(1)} {chapter_m.group(2)}".strip())
            )
            continue

        article_m = _ARTICLE.match(line)
        if article_m:
            flush()
            hierarchy.article = _normalize_line(
                f"Статья {article_m.group(1)} {article_m.group(2)}".strip()
            )
            hierarchy.paragraph = ""
            hierarchy.subpoint = ""
            continue

        table_m = _TABLE_TITLE.search(line)
        clause_m = _CLAUSE_LINE.match(line)
        sub_m = _SUBPOINT.match(line)

        if clause_m:
            flush()
            number = clause_m.group(1)
            rest = clause_m.group(2)
            hierarchy.paragraph = f"Пункт {number}"
            hierarchy.subpoint = ""
            current = StructuredClause(
                clause_number=number,
                text=rest,
                hierarchy=Hierarchy(
                    chapter=hierarchy.chapter,
                    article=hierarchy.article,
                    paragraph=hierarchy.paragraph,
                    subpoint="",
                ),
                page=page,
            )
            # привязать таблицы с этой страницы один раз
            pending = tables_by_page.pop(page, [])
            if pending:
                current.table_text = " || ".join(pending)
                tables_attached += len(pending)
            continue

        if sub_m and current:
            letter, rest = sub_m.group(1), sub_m.group(2)
            parent_number = current.clause_number.split("/")[0] if current.clause_number else ""
            # если текущий — уже подпункт, закрываем и открываем соседний
            if "/" in (current.clause_number or ""):
                flush()
                parent_number = clauses[-1].clause_number.split("/")[0] if clauses else parent_number
            else:
                # дописываем преамбулу пункта, затем выделяем подпункт отдельным clause
                flush()
                parent_number = clauses[-1].clause_number if clauses else parent_number
            sub_number = f"{parent_number}/{letter}" if parent_number else letter
            hierarchy.subpoint = f"Подпункт {letter})"
            current = StructuredClause(
                clause_number=sub_number,
                text=rest,
                hierarchy=Hierarchy(
                    chapter=hierarchy.chapter,
                    article=hierarchy.article,
                    paragraph=hierarchy.paragraph
                    or (f"Пункт {parent_number}" if parent_number else ""),
                    subpoint=hierarchy.subpoint,
                ),
                page=page,
            )
            continue

        if table_m and current and not current.table_text:
            # текстовый заголовок таблицы рядом с пунктом
            current.text = f"{current.text} [{line}]".strip()
            continue

        if current:
            current.text = f"{current.text} {line}".strip()
        elif len(line) >= 40:
            # преамбула без номера — общий блок
            flush()
            current = StructuredClause(
                clause_number="",
                text=line,
                hierarchy=Hierarchy(
                    chapter=hierarchy.chapter,
                    article=hierarchy.article,
                    paragraph=hierarchy.paragraph,
                    subpoint="",
                ),
                page=page,
            )

    flush()

    # оставшиеся таблицы без пункта — отдельные clauses
    for page, table_list in tables_by_page.items():
        for idx, table_text in enumerate(table_list, start=1):
            tables_attached += 1
            clauses.append(
                StructuredClause(
                    clause_number=f"табл.p{page}.{idx}",
                    text=table_text,
                    hierarchy=Hierarchy(chapter=hierarchy.chapter, article=hierarchy.article),
                    table_text=table_text,
                    page=page,
                )
            )

    numbered = [c for c in clauses if c.clause_number]
    return StructuredDocument(
        doc_id=doc_id,
        doc_name=doc_name,
        region_iso=region_iso,
        regulatory_level=regulatory_level,
        doc_type=doc_type,
        doc_version=doc_version,
        clauses=clauses,
        sections_count=len(numbered),
        tables_count=tables_attached,
    )


def build_hierarchical_chunks(doc: StructuredDocument) -> list[HierarchicalChunk]:
    """Вклеивает иерархию в текст чанка (Google-style context inheritance)."""
    chunks: list[HierarchicalChunk] = []
    for idx, clause in enumerate(doc.clauses):
        if not clause.text.strip() and not clause.table_text:
            continue
        parts = [f"[Документ: {doc.doc_name}]"]
        h = clause.hierarchy
        if h.chapter:
            parts.append(f"[{h.chapter}]")
        if h.article:
            parts.append(f"[{h.article}]")
        if h.paragraph:
            parts.append(f"[{h.paragraph}]")
        if h.subpoint:
            parts.append(f"[{h.subpoint}]")
        body = clause.text.strip()
        if clause.table_text:
            body = f"{body} {clause.table_text}".strip() if body else clause.table_text
        if clause.clause_number:
            parts.append(f"[Пункт {clause.clause_number}]")
        embedded = " ".join(parts) + f": {body}"
        clause_key = clause.clause_number or f"block{idx}"
        safe_clause = re.sub(r"[^\w.\-/]+", "_", clause_key)
        chunk_id = f"{doc.region_iso}_{doc.doc_type}_{doc.doc_id}_{safe_clause}_{idx}"
        chunks.append(
            HierarchicalChunk(
                chunk_id=chunk_id,
                region_iso=doc.region_iso,
                regulatory_level=doc.regulatory_level,
                doc_type=doc.doc_type,
                doc_name=doc.doc_name,
                doc_version=doc.doc_version,
                clause_number=clause.clause_number or "без номера",
                text=embedded,
                hierarchy=clause.hierarchy,
                tags=[],
                is_active=True,
            )
        )
    return chunks
