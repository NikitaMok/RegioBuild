"""Commercial API v1 schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InfoV1Request(BaseModel):
    region: str = Field(description="ISO код региона, напр. RU-KDA (или legacy moscow_oblast)")
    object_type: str = Field(description="Тип объекта: автомойка, склад, …")
    telegram_user_id: str | None = None


class CompareV1Request(BaseModel):
    region_a: str
    region_b: str
    object_type: str
    parameter: str | None = Field(
        default=None,
        description="Ось сравнения: parking, fire, sanitary, …; если пусто — все категории объекта",
    )
    telegram_user_id: str | None = None


class CitationV1(BaseModel):
    """Машиночитаемая привязка требования к пункту НПА."""

    document: str = Field(description="Краткое имя НПА: «РНГП МО», «123-ФЗ», «СП 42.13330.2016»")
    clause: str = Field(default="", description="Номер пункта/статьи; пусто, если в источнике нет")
    region: str = Field(description="ISO код региона источника; RU-FED для федеральных норм")
    level: Literal["federal", "regional"]
    last_verified: str | None = Field(
        default=None, description="Дата последней сверки документа с первоисточником"
    )


class RequirementV1(BaseModel):
    category: str
    description: str
    is_specific: bool = Field(
        description="true — норма прямо про этот тип объекта; false — общая применимая норма"
    )
    citation: CitationV1


class RegionValueV1(BaseModel):
    region: str
    value: str
    citation: CitationV1 | None = None


class DifferenceV1(BaseModel):
    category: str
    summary: str
    region_a: RegionValueV1
    region_b: RegionValueV1
    is_specific: bool = True
    level: Literal["federal", "regional"] = "regional"


class SourceDocumentV1(BaseModel):
    region: str
    title: str
    url: str = ""
    last_verified: str | None = None


class AgentV1Response(BaseModel):
    """Ответ v1: human-readable текст + машиночитаемая структура для интеграций."""

    response_text: str
    error: str | None = None
    query_log_id: str | None = None
    guardrail_blocked: bool = False
    region: str | None = None
    object_type: str | None = None

    summary: str | None = Field(default=None, description="Краткий вывод (режим compare)")
    requirements: list[RequirementV1] = Field(
        default_factory=list, description="Режим info: требования с привязкой к пунктам НПА"
    )
    common_requirements: list[RequirementV1] = Field(
        default_factory=list, description="Режим compare: совпадающие требования"
    )
    differences: list[DifferenceV1] = Field(
        default_factory=list, description="Режим compare: различия по регионам"
    )
    sources: list[SourceDocumentV1] = Field(
        default_factory=list, description="Нормативные документы, на которых основан ответ"
    )
