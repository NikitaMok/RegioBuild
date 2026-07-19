from __future__ import annotations

from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field, field_validator

# как в Settings.requirement_categories; "иные_требования" — всё остальное
RequirementCategory = Literal[
    "сроки", "документы", "подключение_к_сетям", "состав_проекта", "иные_требования"
]

_FALLBACK_CATEGORY: RequirementCategory = "иные_требования"

SourceLevel = Literal["федеральный", "региональный"]


def _coerce_category(value: object) -> object:
    if isinstance(value, str) and value not in RequirementCategory.__args__:
        logger.warning(f"LLM вернула незнакомую категорию «{value}», использую «{_FALLBACK_CATEGORY}»")
        return _FALLBACK_CATEGORY
    return value


class RequirementItem(BaseModel):
    category: RequirementCategory
    description: str
    citation: str = Field(description="номер пункта норматива, из которого взято требование")
    is_specific: bool = Field(
        default=True,
        description=(
            "true — норма прямо про этот тип бизнеса; false — общая норма "
            "градостроительного проектирования, которая просто применима к нему"
        ),
    )
    source_level: SourceLevel = Field(
        default="региональный",
        description="'федеральный', если фрагмент взят из СП 42.13330.2016, иначе 'региональный'",
    )

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: object) -> object:
        return _coerce_category(value)


class ExtractionResult(BaseModel):
    region_code: str
    business_type: str
    items: list[RequirementItem] = Field(default_factory=list)


class DifferenceItem(BaseModel):
    category: RequirementCategory
    region_a_value: str = Field(
        description="конкретная формулировка или цифра из норматива региона A, не общая фраза"
    )
    region_b_value: str = Field(
        description="конкретная формулировка или цифра из норматива региона B, не общая фраза"
    )
    summary: str = Field(description="в чём разница между region_a_value и region_b_value, простыми словами")
    is_specific: bool = Field(
        default=True,
        description=(
            "true — норма прямо про этот тип бизнеса; false — общая норма "
            "градостроительного проектирования, которая просто применима к нему"
        ),
    )
    source_level: SourceLevel = Field(
        default="региональный",
        description=(
            "'федеральный', если значения взяты из СП 42.13330.2016 (например, "
            "региональный акт молчит по этому пункту), иначе 'региональный'"
        ),
    )

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: object) -> object:
        return _coerce_category(value)


class ComparisonResult(BaseModel):
    region_a: str
    region_b: str
    business_type: str
    overall_summary: str = Field(
        description="1-2 предложения простым языком: требования в целом похожи или заметно различаются"
    )
    differences: list[DifferenceItem] = Field(default_factory=list)
