from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.regions import REGIONS


class InfoRequest(BaseModel):
    business_type: str = Field(min_length=2, max_length=200, examples=["кафе"])
    region_code: str = Field(examples=list(REGIONS.keys()))
    telegram_user_id: str | None = Field(default=None, max_length=64)


class CompareRequest(BaseModel):
    business_type: str = Field(min_length=2, max_length=200, examples=["кафе"])
    region_a: str = Field(examples=list(REGIONS.keys()))
    region_b: str = Field(examples=list(REGIONS.keys()))
    telegram_user_id: str | None = Field(default=None, max_length=64)


class AgentResponse(BaseModel):
    response_text: str
    error: str | None = None
    query_log_id: str | None = None


class FeedbackRequest(BaseModel):
    query_log_id: str
    vote: Literal["up", "down"]


class RegionInfo(BaseModel):
    code: str
    display_name: str


class RegionsResponse(BaseModel):
    regions: list[RegionInfo]
