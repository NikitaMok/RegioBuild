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

# Некоторые сайты (meganorm.ru) отдают XHTML с прологом <?xml ...?> в начале —
# из-за него bs4 пытается угадать XML и ругается warning'ом, хотя дальше это
# обычный HTML. Пролог для извлечения текста не нужен, поэтому просто срезаем его.
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


def split_into_sections(text: str, min_section_chars: int = 40) -> list[Section]:
    """Разбивает текст документа на пронумерованные пункты.

    Строки без номера в начале считаются продолжением текущего пункта
    (обычная ситуация — перенос строки посреди предложения или таблица).
    Текст до первого найденного номера (шапка, преамбула) отбрасывается,
    если он короче min_section_chars.
    """
    sections: list[Section] = []
    current_number: str | None = None
    current_lines: list[str] = []

    def flush_current_section() -> None:
        if not current_lines:
            return
        text_joined = " ".join(current_lines).strip()
        if current_number is not None or len(text_joined) >= min_section_chars:
            sections.append(Section(number=current_number, text=text_joined))

    for line in text.splitlines():
        match = SECTION_NUMBER_PATTERN.match(line)
        if match:
            flush_current_section()
            current_number = match.group(1)
            current_lines = [match.group(2)]
        else:
            current_lines.append(line)

    flush_current_section()
    return sections


def _iter_body_blocks(document: Document):
    """python-docx не даёт параграфы и таблицы одним потоком в порядке документа,
    приходится обходить XML body вручную — иначе таблицы (а в РНГП именно в них
    указаны конкретные нормативные показатели) выпадут из текста."""
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
