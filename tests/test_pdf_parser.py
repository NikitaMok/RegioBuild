from __future__ import annotations

from app.core.documents import all_document_specs, ingestible_documents
from app.core.regions import FEDERAL_CODE, REGIONS, get_region, resolve_region_code
from app.ingestion.pdf_parser import (
    Hierarchy,
    StructuredClause,
    StructuredDocument,
    build_hierarchical_chunks,
    parse_lines_to_structured,
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
    # 4 federal + 5 RNGP + 2 regional laws + 1 municipal deferred
    assert len(all_docs) == 12
    active = ingestible_documents()
    assert len(active) == 11
    assert all(d.ingest and d.regulatory_level in {"federal", "regional"} for d in active)
    assert not any(d.regulatory_level == "municipal" and d.ingest for d in all_docs)
    deferred = [d for d in all_docs if not d.ingest]
    assert len(deferred) == 1
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


def test_junk_table_columns_not_clauses() -> None:
    doc = parse_lines_to_structured(
        [
            (1, "5.2.3 Расстояние до жилой застройки не менее 50 м."),
            (1, "1 | 2 | 3 Заголовок колонок"),
            (1, "300 | 1,2"),
            (1, "5.2.4 Участок размещают с учётом ветра."),
        ],
        doc_id="T",
        doc_name="тест",
        region_iso="RU-KDA",
        regulatory_level="regional",
        doc_type="RNGP",
        doc_version="t",
    )
    numbers = [c.clause_number for c in doc.clauses if c.clause_number]
    assert "5.2.3" in numbers
    assert "5.2.4" in numbers
    assert "1" not in numbers
    assert "300" not in numbers


def test_part_of_article_not_chapter() -> None:
    doc = parse_lines_to_structured(
        [
            (1, "Статья 35 Объекты"),
            (1, "Часть 2 Требования к размещению"),
            (1, "1. Объект размещают вне жилой зоны."),
        ],
        doc_id="T",
        doc_name="тест",
        region_iso="RU-FED",
        regulatory_level="federal",
        doc_type="law",
        doc_version="t",
    )
    assert doc.clauses
    clause = next(c for c in doc.clauses if c.clause_number == "1")
    assert "Глава" not in (clause.hierarchy.chapter or "")
    assert "Часть 2" in clause.hierarchy.part
    assert "Статья 35" in clause.hierarchy.article


def test_table_title_becomes_table_clause() -> None:
    doc = parse_lines_to_structured(
        [
            (1, "5.5.1 Общие требования к парковке."),
            (1, "Таблица 108 Расчёт машино-мест"),
            (1, "Торговый центр | 1 на 40 м²"),
            (1, "Кафе | 1 на 5 посадочных"),
            (2, "5.5.2 Дополнительные требования."),
        ],
        doc_id="T",
        doc_name="тест",
        region_iso="RU-KDA",
        regulatory_level="regional",
        doc_type="RNGP",
        doc_version="t",
    )
    numbers = [c.clause_number for c in doc.clauses]
    assert "табл.108" in numbers
    table = next(c for c in doc.clauses if c.clause_number == "табл.108")
    assert "машино-мест" in table.text
    assert "Торговый центр" in table.text
    assert doc.tables_count >= 1


def test_table_title_with_n_prefix() -> None:
    doc = parse_lines_to_structured(
        [
            (1, "Таблица N 1 Нормы расчёта стоянок"),
            (1, "Склады 6–8 машино-мест"),
        ],
        doc_id="T",
        doc_name="тест",
        region_iso="RU-MOS",
        regulatory_level="regional",
        doc_type="RNGP",
        doc_version="t",
    )
    assert any(c.clause_number == "табл.1" for c in doc.clauses)
    assert doc.tables_count >= 1
