from __future__ import annotations

from dataclasses import dataclass

from app.ingestion.parser import Section

DEFAULT_MAX_CHARS = 800
DEFAULT_OVERLAP = 150


@dataclass
class Chunk:
    region_code: str
    section_number: str | None
    text: str

    @property
    def char_count(self) -> int:
        return len(self.text)


def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    pieces = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            # режем по пробелу, а не посреди слова
            space_pos = text.rfind(" ", start, end)
            if space_pos > start:
                end = space_pos
        pieces.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)

    return [piece for piece in pieces if piece]


def chunk_sections(
    sections: list[Section],
    region_code: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    chunks = []
    for section in sections:
        for piece in _split_long_text(section.text, max_chars, overlap):
            chunks.append(Chunk(region_code=region_code, section_number=section.number, text=piece))
    return chunks
