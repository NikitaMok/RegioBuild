from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

# Пункты РНГП нумеруются в начале строки: "1.", "2.3", "4.5.2." и т.д.
SECTION_NUMBER_PATTERN = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){0,4})\.?\s+(\S.*)$")

# строки таблиц вида «1 | 2 | 3 …» или «300 | 1,2» — не пункты НПА
_TABLE_ROW_AFTER_NUMBER = re.compile(r"^\|")
_TABLE_CELLS = re.compile(r"\s\|\s")
_TABLE_TITLE = re.compile(r"Таблица\s+(\d+)", re.IGNORECASE)

# meganorm отдаёт XHTML с <?xml ...?> — bs4 ругается, пролог срезаем
XML_PROLOG_PATTERN = re.compile(rb"^\s*<\?xml[^>]*\?>\s*")

TAGS_TO_DROP = ("script", "style", "nav", "header", "footer", "noscript", "form")


@dataclass
class Section:
    number: str | None
    text: str


def extract_text_from_html(html: bytes | str) -> str:
    if isinstance(html, bytes):
        html = XML_PROLOG_PATTERN.sub(b"", html, count=1)
    soup = BeautifulSoup(html, "lxml")

    for tag_name in TAGS_TO_DROP:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
    return "\n".join(line for line in lines if line)


def _is_real_section_header(number: str, rest: str) -> bool:
    """Отсекает колонки/ячейки таблиц, которые regex путает с пунктами НПА."""
    cleaned = (rest or "").strip()
    if not cleaned:
        return False
    if _TABLE_ROW_AFTER_NUMBER.match(cleaned) or cleaned.startswith("|"):
        return False
    # «1 | 2 | 3 Заголовок» — нумерация колонок таблицы
    if _TABLE_CELLS.search(cleaned):
        return False
    # вместимость/площадь вроде «300 | 1,2» уже отсечена выше; голые 100+ без точки
    # часто ячейки таблиц, попавшие в начало строки после разбиения docx
    if "." not in number and number.isdigit() and int(number) >= 100:
        return False
    return True


def split_into_sections(text: str, min_section_chars: int = 40) -> list[Section]:
    """Разбивает текст на пронумерованные пункты; строки без номера — продолжение текущего."""
    sections: list[Section] = []
    current_number: str | None = None
    current_lines: list[str] = []
    active_table: str | None = None

    def flush_current_section() -> None:
        nonlocal current_number, current_lines
        if not current_lines:
            return
        text_joined = " ".join(current_lines).strip()
        if current_number is not None or len(text_joined) >= min_section_chars:
            sections.append(Section(number=current_number, text=text_joined))
        current_lines = []

    for line in text.splitlines():
        table_match = _TABLE_TITLE.search(line)
        if table_match:
            active_table = f"табл.{table_match.group(1)}"

        match = SECTION_NUMBER_PATTERN.match(line)
        if match and _is_real_section_header(match.group(1), match.group(2)):
            flush_current_section()
            current_number = match.group(1)
            current_lines = [match.group(2)]
            # новый «настоящий» пункт сбрасывает привязку к таблице
            if "." in current_number:
                active_table = None
        else:
            # строки таблицы без пункта — копим под табл.N, а не под чужим/фейковым номером
            is_table_line = bool(
                _TABLE_CELLS.search(line) or line.strip().startswith("|")
            )
            if active_table and is_table_line:
                if current_number != active_table:
                    flush_current_section()
                    current_number = active_table
                    current_lines = [line]
                else:
                    current_lines.append(line)
            else:
                current_lines.append(line)

    flush_current_section()
    return sections


def _iter_body_blocks(document: Document):
    """Обход body вручную: иначе python-docx теряет таблицы."""
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def extract_text_from_docx(path: Path) -> str:
    document = Document(str(path))
    lines: list[str] = []

    for block in _iter_body_blocks(document):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if text:
                lines.append(text)
        else:
            for row in block.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    lines.append(" | ".join(cells))

    return "\n".join(lines)


def parse_region_document(raw_path: Path) -> list[Section]:
    if raw_path.suffix.lower() == ".docx":
        text = extract_text_from_docx(raw_path)
    else:
        text = extract_text_from_html(raw_path.read_bytes())
    return split_into_sections(text)
