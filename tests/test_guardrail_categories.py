from __future__ import annotations

from app.agent.guardrail import claim_numbers_supported
from app.core.object_categories import categories_for_object, query_phrases_for_object
from app.vectorstore.types import RetrievedChunk


def test_object_categories_carwash() -> None:
    cats = categories_for_object("автомойка")
    assert "parking" in cats
    assert "sanitary" in cats
    phrases = query_phrases_for_object("автомойка")
    assert phrases
    assert any("автомойка" in p for p in phrases)


def test_guardrail_blocks_invented_percent() -> None:
    chunks = [
        RetrievedChunk(
            id="1",
            text="Требуется не менее 6 метров от границы участка.",
            region_code="RU-NVS",
            section_number="1.4",
            category=None,
            distance=0.1,
        )
    ]
    assert claim_numbers_supported("отступ 6 метров", chunks)
    assert not claim_numbers_supported("нужно озеленение 37% территории", chunks)


def test_guardrail_ignores_npa_header_dates() -> None:
    chunks = [
        RetrievedChunk(
            id="1",
            text="Для автомоек расстояние не менее 50 метров.",
            region_code="RU-KDA",
            section_number="5.5.153",
            category=None,
            distance=0.1,
        )
    ]
    headerish = (
        "Правовое регулирование: Постановление от 17.08.2015 N 713/30 "
        "(проверено 2026-07-22). Федеральный уровень: СП 42 и 123-ФЗ. "
        "Автомойка: 50 метров по п. 5.5.153."
    )
    assert claim_numbers_supported(headerish, chunks)
