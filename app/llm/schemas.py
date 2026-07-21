from __future__ import annotations

from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field, field_validator

RequirementCategory = Literal[
    "земельно_правовые",
    "градостроительные",
    "пожарная_безопасность",
    "санитарные_экологические",
    "архитектурный_облик",
    "дорожное_согласование",
    "налоги_поддержка",
    "процедуры_согласования",
    "подключение_к_сетям",
    "сроки_и_документы",
    # legacy (coerce → новые)
    "сроки",
    "документы",
    "состав_проекта",
    "иные_требования",
]

_FALLBACK_CATEGORY: RequirementCategory = "градостроительные"

_CATEGORY_ALIASES: dict[str, RequirementCategory] = {
    "сроки": "сроки_и_документы",
    "документы": "сроки_и_документы",
    "состав_проекта": "градостроительные",
    "иные_требования": "градостроительные",
}

SourceLevel = Literal["федеральный", "региональный"]


def _coerce_category(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value in _CATEGORY_ALIASES:
        return _CATEGORY_ALIASES[value]
    allowed = {
        "земельно_правовые",
        "градостроительные",
        "пожарная_безопасность",
        "санитарные_экологические",
        "архитектурный_облик",
        "дорожное_согласование",
        "налоги_поддержка",
        "процедуры_согласования",
        "подключение_к_сетям",
        "сроки_и_документы",
    }
    if value not in allowed:
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
        description="'федеральный', если фрагмент взят из федерального НПА, иначе 'региональный'",
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
            "'федеральный', если значения взяты из федерального НПА "
            "(например, региональный акт молчит по этому пункту), иначе 'региональный'"
        ),
    )

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: object) -> object:
        return _coerce_category(value)


class CommonRequirementItem(BaseModel):
    """Норма, которая совпадает или одинаково применима в обоих регионах."""

    category: RequirementCategory
    description: str
    citation: str = Field(default="", description="номер пункта, если есть в фрагментах")
    is_specific: bool = True
    source_level: SourceLevel = "региональный"

    @field_validator("category", mode="before")
    @classmethod
    def _normalize_category(cls, value: object) -> object:
        return _coerce_category(value)


class ComparisonResult(BaseModel):
    region_a: str
    region_b: str
    business_type: str
    overall_summary: str = Field(
        description="1-2 предложения простым языком: что совпадает и что отличается при расширении бизнеса"
    )
    common_requirements: list[CommonRequirementItem] = Field(
        default_factory=list,
        description="требования, которые совпадают или одинаково опираются на федеральные нормы",
    )
    differences: list[DifferenceItem] = Field(default_factory=list)
