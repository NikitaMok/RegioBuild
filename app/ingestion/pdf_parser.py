"""Иерархический парсинг PDF НПА → structured clauses + micro-chunks.

Наследование контекста: в текст чанка вклеиваются документ / глава / пункт.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger


def _pdfplumber():
    """Ленивый импорт: unit-тесты иерархии не требуют pdfplumber в CI."""
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "для парсинга PDF установите pdfplumber (см. requirements.txt)"
        ) from exc
    return pdfplumber

# пункт вида 5.2.3 / 5.2 / 12
_CLAUSE_LINE = re.compile(
    r"^(?:п(?:ункт)?\.?\s*)?(\d{1,3}(?:\.\d{1,3}){0,5})\.?\s+(.+)$",
    re.IGNORECASE,
)
_SUBPOINT = re.compile(r"^([а-яa-z])\)\s+(.+)$", re.IGNORECASE)
# «часть» статьи — не глава; глава/раздел отдельно
_CHAPTER = re.compile(
    r"^(?:глава|раздел)\s+([IVXLC\d]+|[А-ЯA-Z\d\.]+)[\.\s:—-]*(.*)$",
    re.IGNORECASE,
)
_PART = re.compile(
    r"^часть\s+(\d+(?:\.\d+)*)[\.\s:—-]*(.*)$",
    re.IGNORECASE,
)
_ARTICLE = re.compile(
    r"^(?:статья|ст\.)\s*(\d+(?:\.\d+)*)[\.\s:—-]*(.*)$",
    re.IGNORECASE,
)
_TABLE_TITLE = re.compile(
    r"таблица\s+(?:[nN№#]\s*)?(\d+(?:\.\d+)*[а-яa-z]?)",
    re.IGNORECASE,
)
# как в DOCX parser: колонки таблиц ≠ пункты НПА
_TABLE_ROW_AFTER_NUMBER = re.compile(r"^\|")
_TABLE_CELLS = re.compile(r"\s\|\s")


@dataclass
class Hierarchy:
    chapter: str = ""
    article: str = ""
    part: str = ""
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


def _is_real_clause_header(number: str, rest: str) -> bool:
    """Отсекает титульную/табличную нумерацию, которую regex путает с пунктами."""
    cleaned = (rest or "").strip()
    if not cleaned:
        return False
    if _TABLE_ROW_AFTER_NUMBER.match(cleaned) or cleaned.startswith("|"):
        return False
    if _TABLE_CELLS.search(cleaned):
        return False
    # голые 100+ без точки — часто ячейки таблиц / колонтитулы
    if "." not in number and number.isdigit() and int(number) >= 100:
        return False
    # «1. Текст» на титуле с одной цифрой и очень коротким хвостом — шум
    if "." not in number and number in {"1", "2", "3"} and len(cleaned) < 12:
        return False
    return True


def _looks_like_table_row(line: str) -> bool:
    return bool(_TABLE_CELLS.search(line) or line.strip().startswith("|"))


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
    pdfplumber = _pdfplumber()
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
        pdfplumber = _pdfplumber()
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


def parse_lines_to_structured(
    lines: list[tuple[int, str]],
    *,
    doc_id: str,
    doc_name: str,
    region_iso: str,
    regulatory_level: str,
    doc_type: str,
    doc_version: str,
    page_tables: list[tuple[int, str]] | None = None,
) -> StructuredDocument:
    """Разбор уже извлечённых строк PDF (+ опционально pdfplumber-таблицы)."""
    # pdfplumber-таблицы: не клеим все на первый пункт страницы —
    # держим очередь и отдаём ближайшему пункту/заголовку таблицы, иначе orphan.
    tables_by_page: dict[int, list[str]] = {}
    for page, table_text in page_tables or []:
        tables_by_page.setdefault(page, []).append(table_text)

    hierarchy = Hierarchy()
    clauses: list[StructuredClause] = []
    current: StructuredClause | None = None
    tables_attached = 0
    active_table_id: str | None = None

    def flush() -> None:
        nonlocal current
        if current and (current.text.strip() or current.table_text):
            clauses.append(current)
        current = None

    def attach_pending_pdf_tables(page: int, target: StructuredClause) -> None:
        nonlocal tables_attached
        pending = tables_by_page.pop(page, [])
        if not pending:
            return
        # максимум одна «ближайшая» pdfplumber-таблица к пункту; остальное — orphan
        first, *rest = pending
        if target.table_text:
            target.table_text = f"{target.table_text} || {first}"
        else:
            target.table_text = first
        tables_attached += 1
        if rest:
            tables_by_page[page] = rest

    def start_table_clause(table_id: str, page: int, title_line: str) -> None:
        nonlocal current, tables_attached, active_table_id
        flush()
        active_table_id = table_id
        current = StructuredClause(
            clause_number=table_id,
            text=title_line,
            hierarchy=Hierarchy(
                chapter=hierarchy.chapter,
                article=hierarchy.article,
                part=hierarchy.part,
                paragraph="",
                subpoint="",
            ),
            page=page,
        )
        attach_pending_pdf_tables(page, current)
        tables_attached += 1  # текстовый заголовок таблицы тоже считаем

    for page, line in lines:
        chapter_m = _CHAPTER.match(line)
        if chapter_m:
            flush()
            active_table_id = None
            hierarchy = Hierarchy(
                chapter=_normalize_line(f"Глава {chapter_m.group(1)} {chapter_m.group(2)}".strip())
            )
            continue

        article_m = _ARTICLE.match(line)
        if article_m:
            flush()
            active_table_id = None
            hierarchy.article = _normalize_line(
                f"Статья {article_m.group(1)} {article_m.group(2)}".strip()
            )
            hierarchy.part = ""
            hierarchy.paragraph = ""
            hierarchy.subpoint = ""
            continue

        part_m = _PART.match(line)
        if part_m:
            flush()
            active_table_id = None
            hierarchy.part = _normalize_line(
                f"Часть {part_m.group(1)} {part_m.group(2)}".strip()
            )
            hierarchy.paragraph = ""
            hierarchy.subpoint = ""
            continue

        table_m = _TABLE_TITLE.search(line)
        if table_m:
            start_table_clause(f"табл.{table_m.group(1)}", page, line)
            continue

        clause_m = _CLAUSE_LINE.match(line)
        sub_m = _SUBPOINT.match(line)

        if clause_m and _is_real_clause_header(clause_m.group(1), clause_m.group(2)):
            flush()
            active_table_id = None
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
                    part=hierarchy.part,
                    paragraph=hierarchy.paragraph,
                    subpoint="",
                ),
                page=page,
            )
            attach_pending_pdf_tables(page, current)
            continue

        if sub_m and current and not (current.clause_number or "").startswith("табл."):
            letter, rest = sub_m.group(1), sub_m.group(2)
            parent_number = current.clause_number.split("/")[0] if current.clause_number else ""
            if "/" in (current.clause_number or ""):
                flush()
                parent_number = clauses[-1].clause_number.split("/")[0] if clauses else parent_number
            else:
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
                    part=hierarchy.part,
                    paragraph=hierarchy.paragraph
                    or (f"Пункт {parent_number}" if parent_number else ""),
                    subpoint=hierarchy.subpoint,
                ),
                page=page,
            )
            continue

        # строки таблицы после «Таблица N» — копим под табл.N, не под чужим пунктом
        if active_table_id and current and current.clause_number == active_table_id:
            if _looks_like_table_row(line) or not _CLAUSE_LINE.match(line):
                current.text = f"{current.text} {line}".strip()
                if not current.table_text and _looks_like_table_row(line):
                    current.table_text = line
                continue

        if current:
            current.text = f"{current.text} {line}".strip()
        elif len(line) >= 40:
            flush()
            current = StructuredClause(
                clause_number="",
                text=line,
                hierarchy=Hierarchy(
                    chapter=hierarchy.chapter,
                    article=hierarchy.article,
                    part=hierarchy.part,
                    paragraph=hierarchy.paragraph,
                    subpoint="",
                ),
                page=page,
            )

    flush()

    # оставшиеся pdfplumber-таблицы без пункта — отдельные clauses
    for page, table_list in tables_by_page.items():
        for idx, table_text in enumerate(table_list, start=1):
            tables_attached += 1
            clauses.append(
                StructuredClause(
                    clause_number=f"табл.p{page}.{idx}",
                    text=table_text,
                    hierarchy=Hierarchy(
                        chapter=hierarchy.chapter,
                        article=hierarchy.article,
                        part=hierarchy.part,
                    ),
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
    return parse_lines_to_structured(
        extract_pdf_lines(path),
        doc_id=doc_id,
        doc_name=doc_name,
        region_iso=region_iso,
        regulatory_level=regulatory_level,
        doc_type=doc_type,
        doc_version=doc_version,
        page_tables=extract_pdf_tables(path),
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
        if h.part:
            parts.append(f"[{h.part}]")
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
