from __future__ import annotations

from typing import Literal, Optional, TypedDict

from app.llm.schemas import ComparisonResult, ExtractionResult
from app.vectorstore.types import RetrievedChunk


class AgentState(TypedDict, total=False):
    mode: Literal["info", "compare"]
    business_type: str
    business_type_raw: Optional[str]
    region_a: str
    region_b: Optional[str]
    transformed_query: Optional[str]
    categories: list[str]

    retrieved_a: list[RetrievedChunk]
    retrieved_b: list[RetrievedChunk]
    retrieved_federal: list[RetrievedChunk]

    extraction: Optional[ExtractionResult]
    comparison: Optional[ComparisonResult]

    response_text: str
    error: Optional[str]
    # aspect/retrieval: отказ как основной ответ (без «Не удалось получить ответ»)
    refusal_kind: Optional[str]
    guardrail_blocked: bool
