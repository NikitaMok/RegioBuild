from __future__ import annotations

from app.core.regions import FEDERAL_CODE, REGIONS, all_documents, get_region
from app.ingestion.federal_sources import all_curated_chunks


def test_regions_loaded_from_yaml() -> None:
    assert "moscow_oblast" in REGIONS
    assert len(REGIONS) == 5
    moscow = get_region("moscow_oblast")
    assert moscow.display_name == "Московская область"
    assert "713/30" in moscow.document_title


def test_federal_document_present() -> None:
    docs = all_documents()
    assert FEDERAL_CODE in docs
    assert "СП 42.13330" in docs[FEDERAL_CODE].document_title


def test_curated_federal_sources_cover_fz123_and_sanpin() -> None:
    chunks = all_curated_chunks()
    labels = {c.source_label for c in chunks}
    assert any("123-ФЗ" in label for label in labels)
    assert any("СанПиН" in label for label in labels)
    assert any(c.region_code == "novosibirsk_oblast" for c in chunks)


def test_curated_krasnodar_carwash_and_sanpin_meters() -> None:
    chunks = all_curated_chunks()
    by_section = {c.section_number: c for c in chunks}
    assert "5.5.153" in by_section
    assert "автомоек" in by_section["5.5.153"].text.lower()
    assert "4.3.20" in by_section
    assert "автомоек" in by_section["4.3.20"].text.lower()
    assert "табл.108" in by_section
    assert "автомойки" in by_section["табл.108"].text.lower()
    assert "СанПиН/7.1.3" in by_section
    assert "100" in by_section["СанПиН/7.1.3"].text
    assert "50" in by_section["СанПиН/7.1.3"].text
    assert "123-ФЗ/69" in by_section
    assert "СанПиН/7.1.4" in by_section
    assert "5.2.258" in by_section
    assert by_section["5.2.258"].region_code == "tatarstan"

