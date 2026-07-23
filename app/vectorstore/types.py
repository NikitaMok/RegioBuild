from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievedChunk:
    id: str
    text: str
    region_code: str
    section_number: str | None
    category: str | None
    distance: float
    tags: list[str] = field(default_factory=list)
    doc_type: str = ""
