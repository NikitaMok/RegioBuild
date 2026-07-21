from __future__ import annotations

from app.llm.prompts import build_comparison_prompt, build_extraction_prompt
from app.vectorstore.retriever import RetrievedChunk


def _chunk(text: str, section_number: str = "1.1") -> RetrievedChunk:
    return RetrievedChunk(
        id="fake-id",
        text=text,
        region_code="moscow_oblast",
        section_number=section_number,
        category=None,
        distance=0.1,
    )


def test_extraction_prompt_includes_federal_block_separately_from_regional() -> None:
    prompt = build_extraction_prompt(
        "склад",
        "moscow_oblast",
        [_chunk("Региональная норма про склады.")],
        [_chunk("Федеральная норма СП 42.13330.")],
    )

    assert "Региональная норма про склады" in prompt
    assert "Федеральная норма СП 42.13330" in prompt
    assert "федеральных норм" in prompt


def test_extraction_prompt_handles_missing_federal_chunks() -> None:
    prompt = build_extraction_prompt("склад", "moscow_oblast", [_chunk("Что-то про склады.")])
    assert "фрагменты не найдены" in prompt


def test_comparison_prompt_includes_shared_federal_block() -> None:
    prompt = build_comparison_prompt(
        "склад",
        "moscow_oblast",
        [_chunk("Норма региона A.")],
        "krasnodar_krai",
        [_chunk("Норма региона B.")],
        [_chunk("Федеральная норма.")],
    )

    assert "Норма региона A" in prompt
    assert "Норма региона B" in prompt
    assert "Федеральная норма" in prompt
    assert "федеральных норм" in prompt
    assert "common_requirements" in prompt
    assert "Московская область" in prompt
