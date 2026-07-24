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
        "(проверено 2026-07-22). Федеральные нормы: СП 42 и 123-ФЗ. "
        "Автомойка: 50 метров по п. 5.5.153."
    )
    assert claim_numbers_supported(headerish, chunks)


def test_guardrail_ignores_npa_requisite_numbers_in_body() -> None:
    chunks = [
        RetrievedChunk(
            id="1",
            text="Для складов применяются федеральные нормы.",
            region_code="RU-MOS",
            section_number="5.26",
            category=None,
            distance=0.1,
        )
    ]
    body = (
        "По Постановлению № 713/30 парковка по приложению. "
        "В Республике Татарстан — Постановление № 1071. "
        "Ориентир 450 метров вне фрагментов."
    )
    # 713, 1071 — реквизиты; одно лишнее число (450) — ещё не блок
    assert claim_numbers_supported(body, chunks)


def test_build_guardrail_warning_keeps_docs() -> None:
    from app.agent.guardrail import build_guardrail_warning

    chunks = [
        RetrievedChunk(
            id="1",
            text="[Документ: Нормативы градостроительного проектирования Московской области] текст",
            region_code="RU-MOS",
            section_number="1",
            category=None,
            distance=0.1,
        )
    ]
    warning = build_guardrail_warning(chunks)
    assert "заблокирован" not in warning.lower()
    assert "расхождения" in warning.lower()
    assert "Нормативы градостроительного проектирования Московской области" in warning
