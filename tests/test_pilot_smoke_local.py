"""Локальный smoke retrieval по опорным curated-секциям (без LLM / без Bothost)."""

from __future__ import annotations

from app.agent import nodes
from app.ingestion.federal_sources import all_curated_chunks
from app.vectorstore.types import RetrievedChunk


def test_local_wave1_curated_anchors_present() -> None:
    chunks = all_curated_chunks()
    by_key = {(c.region_code, c.section_number): c for c in chunks}
    assert ("krasnodar_krai", "5.5.153") in by_key or any(
        c.section_number and "5.5.153" in c.section_number for c in chunks
    )
    # ISO RU-FED + legacy alias «federal»
    federal_sections = {
        c.section_number
        for c in chunks
        if c.region_code in {"federal", "RU-FED"}
    }
    assert any("123-ФЗ" in (s or "") or "СанПиН" in (s or "") for s in federal_sections)


def test_honest_fallback_still_wired() -> None:
    junk = [
        RetrievedChunk(
            id="j",
            text="шум",
            region_code="novosibirsk_oblast",
            section_number="1",
            category=None,
            distance=0.1,
        )
    ]
    usable = nodes._filter_usable_chunks(junk)
    assert usable == [] or all(nodes._section_rank_quality(c.section_number) < 2 for c in usable)
