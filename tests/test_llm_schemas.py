from __future__ import annotations

from app.llm.schemas import RequirementItem


def test_known_category_is_kept_as_is() -> None:
    item = RequirementItem(
        category="сроки_и_документы",
        description="Срок выдачи — 10 дней.",
        citation="1.1",
    )
    assert item.category == "сроки_и_документы"


def test_legacy_category_is_coerced() -> None:
    item = RequirementItem(category="сроки", description="Срок выдачи — 10 дней.", citation="1.1")
    assert item.category == "сроки_и_документы"


def test_unknown_category_falls_back_to_other() -> None:
    item = RequirementItem(category="парковочные места", description="...", citation="4.5")
    assert item.category == "градостроительные"


def test_is_specific_defaults_to_true_when_llm_omits_it() -> None:
    item = RequirementItem(category="сроки_и_документы", description="...", citation="1.1")
    assert item.is_specific is True


def test_empty_source_level_coerces_to_regional() -> None:
    item = RequirementItem.model_validate(
        {
            "category": "градостроительные",
            "description": "1 машино-место на 40 м²",
            "citation": "5.5.153",
            "source_level": "",
        }
    )
    assert item.source_level == "региональный"


def test_source_level_inferred_federal_from_citation() -> None:
    item = RequirementItem.model_validate(
        {
            "category": "пожарная_безопасность",
            "description": "Эвакуация",
            "citation": "123-ФЗ/88",
            "source_level": "",
        }
    )
    assert item.source_level == "федеральный"


def test_extraction_accepts_empty_source_levels_in_items() -> None:
    from app.llm.schemas import ExtractionResult

    result = ExtractionResult.model_validate(
        {
            "region_code": "krasnodar_krai",
            "business_type": "торговый центр",
            "items": [
                {
                    "category": "градостроительные",
                    "description": "Парковка",
                    "citation": "табл.108",
                    "is_specific": True,
                    "source_level": "региональный",
                },
                {
                    "category": "санитарные_экологические",
                    "description": "СЗЗ",
                    "citation": "СанПиН/2.1",
                    "is_specific": False,
                    "source_level": "",
                },
            ],
        }
    )
    assert result.items[1].source_level == "федеральный"
