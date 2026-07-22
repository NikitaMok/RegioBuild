"""Commercial API v1 schemas."""

from __future__ import annotations

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


class AgentV1Response(BaseModel):
    response_text: str
    error: str | None = None
    query_log_id: str | None = None
    guardrail_blocked: bool = False
    region: str | None = None
    object_type: str | None = None
