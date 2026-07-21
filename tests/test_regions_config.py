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
