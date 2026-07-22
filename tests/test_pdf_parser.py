from __future__ import annotations

from app.core.documents import all_document_specs, ingestible_documents
from app.core.regions import FEDERAL_CODE, REGIONS, get_region, resolve_region_code
from app.ingestion.pdf_parser import (
    Hierarchy,
    StructuredClause,
    StructuredDocument,
    build_hierarchical_chunks,
)


def test_iso_regions_and_aliases() -> None:
    assert "RU-MOS" in REGIONS
    assert len(REGIONS) == 5
    assert resolve_region_code("moscow_oblast") == "RU-MOS"
    assert resolve_region_code("RU-MOS") == "RU-MOS"
    assert get_region("krasnodar_krai").code == "RU-KDA"
    assert FEDERAL_CODE == "RU-FED"
    assert resolve_region_code("federal") == "RU-FED"


def test_documents_manifest_scope() -> None:
    all_docs = all_document_specs()
    assert len(all_docs) == 17
    active = ingestible_documents()
    assert all(d.ingest and d.regulatory_level in {"federal", "regional"} for d in active)
    assert not any(d.regulatory_level == "municipal" and d.ingest for d in all_docs)
    deferred = [d for d in all_docs if not d.ingest]
    assert len(deferred) >= 5
    assert all(d.regulatory_level == "municipal" for d in deferred)


def test_hierarchical_chunk_embeds_context() -> None:
    doc = StructuredDocument(
        doc_id="TEST_DOC",
        doc_name="РНГП тест",
        region_iso="RU-NVS",
        regulatory_level="regional",
        doc_type="RNGP",
        doc_version="2026",
        clauses=[
            StructuredClause(
                clause_number="1.4",
                text="Расстояние должно быть не менее 6 метров.",
                hierarchy=Hierarchy(
                    chapter="Глава 2",
                    article="",
                    paragraph="Пункт 1.4",
                    subpoint="Подпункт б)",
                ),
            )
        ],
        sections_count=1,
        tables_count=0,
    )
    chunks = build_hierarchical_chunks(doc)
    assert len(chunks) == 1
    text = chunks[0].text
    assert "[Документ: РНГП тест]" in text
    assert "[Глава 2]" in text
    assert "[Пункт 1.4]" in text
    assert "6 метров" in text
    assert chunks[0].region_iso == "RU-NVS"
