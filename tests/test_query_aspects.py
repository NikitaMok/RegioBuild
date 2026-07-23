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
