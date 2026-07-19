from __future__ import annotations

from typing import Literal, Optional, TypedDict

from app.llm.schemas import ComparisonResult, ExtractionResult
from app.vectorstore.retriever import RetrievedChunk


class AgentState(TypedDict, total=False):
    mode: Literal["info", "compare"]
    business_type: str
    business_type_raw: Optional[str]
    region_a: str
    region_b: Optional[str]

    retrieved_a: list[RetrievedChunk]
    retrieved_b: list[RetrievedChunk]
    # федеральный слой (СП 42.13330.2016) — общий фон для любого региона,
    # подтягивается один раз независимо от mode (см. retrieve_chunks в nodes.py)
    retrieved_federal: list[RetrievedChunk]

    extraction: Optional[ExtractionResult]
    comparison: Optional[ComparisonResult]

    response_text: str
    error: Optional[str]
