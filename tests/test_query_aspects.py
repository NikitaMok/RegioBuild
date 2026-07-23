from app.core.query_aspects import (
    aspects_supported,
    detect_aspects,
    refusal_for_unsupported_aspects,
)
from app.vectorstore.types import RetrievedChunk


def test_detect_plot_area_aspect() -> None:
    aspects = detect_aspects(
        "Складские здания в Свердловской области — нормы по площади участка?"
    )
    assert len(aspects) == 1
    assert aspects[0].key == "plot_area"


def test_detect_plot_area_norms_po_uchastku() -> None:
    aspects = detect_aspects(
        "Нормы по участку для складских зданий в Свердловской области???"
    )
    assert len(aspects) == 1
    assert aspects[0].key == "plot_area"


def test_plain_warehouse_not_plot_aspect() -> None:
    assert detect_aspects("склад") == []


def test_plot_area_unsupported_without_evidence() -> None:
    aspects = detect_aspects("нормы по площади участка для склада")
    chunks = [
        RetrievedChunk(
            id="1",
            text="Санитарно-защитная зона для складов II–III класса — 300 м.",
            region_code="RU-SVE",
            section_number="7.1",
            category=None,
            distance=0.1,
        )
    ]
    assert not aspects_supported(aspects, chunks)
    msg = refusal_for_unsupported_aspects(
        aspects, business_type="склад", region_label="Свердловской области"
    )
    assert "площади" in msg.lower() or "участк" in msg.lower()
    assert "ПЗЗ" in msg
    assert "индекс" not in msg.lower()
    assert "фрагмент" not in msg.lower()


def test_plot_area_szz_meters_not_enough_evidence() -> None:
    """СЗЗ «300 м» без площади участка — не опора для plot_area."""
    aspects = detect_aspects(
        "Нормы по площади участка для складов в Свердловской области"
    )
    chunks = [
        RetrievedChunk(
            id="1",
            text="Санитарно-защитная зона для складов II–III класса — 300 м. "
            "Противопожарные расстояния по ст. 69 123-ФЗ.",
            region_code="RU-SVE",
            section_number="7.1",
            category=None,
            distance=0.1,
        )
    ]
    assert aspects
    assert not aspects_supported(aspects, chunks)


def test_plot_area_unsupported_for_uchastok_synonym() -> None:
    aspects = detect_aspects("Нормы по участку для складских зданий")
    chunks = [
        RetrievedChunk(
            id="1",
            text="Расчётные показатели обеспеченности территории для складов "
            "устанавливаются региональными нормативами. Специальные нормы "
            "по пожарной безопасности применяются федеральные.",
            region_code="RU-SVE",
            section_number="склад",
            category=None,
            distance=0.1,
        )
    ]
    assert not aspects_supported(aspects, chunks)
