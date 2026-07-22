"""Состояние агента → машиночитаемая структура API v1.

HTML-рендер остаётся для Telegram; интеграторам нужен JSON с привязкой
каждого требования к пункту НПА и уровню регулирования.
"""

from __future__ import annotations

from app.core.npa_titles import short_federal_cite_from_citation, short_npa_cite
from app.core.regions import FEDERAL_CODE, FEDERAL_DOCUMENT, get_region
from app.api.schemas_v1 import (
    CitationV1,
    DifferenceV1,
    RegionValueV1,
    RequirementV1,
    SourceDocumentV1,
)
from app.llm.schemas import (
    CommonRequirementItem,
    ComparisonResult,
    DifferenceItem,
    ExtractionResult,
    RequirementItem,
)

_EMPTY_CLAUSE_MARKERS = {"", "пункт не указан", "без номера", "n/a", "-", "—"}


def _clean_clause(citation: str) -> str:
    cleaned = (citation or "").strip()
    if cleaned.lower() in _EMPTY_CLAUSE_MARKERS:
        return ""
    return cleaned


def _citation(citation: str, source_level: str, region_code: str) -> CitationV1:
    clause = _clean_clause(citation)
    if source_level == "федеральный":
        return CitationV1(
            document=short_federal_cite_from_citation(clause),
            clause=clause,
            region=FEDERAL_CODE,
            level="federal",
            last_verified=FEDERAL_DOCUMENT.last_verified,
        )
    region = get_region(region_code)
    return CitationV1(
        document=short_npa_cite(region.document_title),
        clause=clause,
        region=region.code,
        level="regional",
        last_verified=region.last_verified,
    )


def _requirement(
    item: RequirementItem | CommonRequirementItem, region_code: str
) -> RequirementV1:
    return RequirementV1(
        category=item.category,
        description=item.description,
        is_specific=item.is_specific,
        citation=_citation(item.citation, item.source_level, region_code),
    )


def requirements_from_extraction(extraction: ExtractionResult) -> list[RequirementV1]:
    return [_requirement(item, extraction.region_code) for item in extraction.items]


def _difference(diff: DifferenceItem, region_a: str, region_b: str) -> DifferenceV1:
    level = "federal" if diff.source_level == "федеральный" else "regional"

    def _side(region_code: str, value: str, citation: str) -> RegionValueV1:
        clause = _clean_clause(citation)
        return RegionValueV1(
            region=get_region(region_code).code,
            value=value,
            citation=_citation(citation, diff.source_level, region_code) if clause else None,
        )

    return DifferenceV1(
        category=diff.category,
        summary=diff.summary,
        region_a=_side(region_a, diff.region_a_value, diff.citation_a),
        region_b=_side(region_b, diff.region_b_value, diff.citation_b),
        is_specific=diff.is_specific,
        level=level,
    )


def differences_from_comparison(comparison: ComparisonResult) -> list[DifferenceV1]:
    return [
        _difference(diff, comparison.region_a, comparison.region_b)
        for diff in comparison.differences
    ]


def commons_from_comparison(comparison: ComparisonResult) -> list[RequirementV1]:
    return [_requirement(item, comparison.region_a) for item in comparison.common_requirements]


def sources_for_regions(region_codes: list[str]) -> list[SourceDocumentV1]:
    """Региональные НПА запрошенных регионов + федеральный слой."""
    sources: list[SourceDocumentV1] = []
    seen: set[str] = set()
    for code in [*region_codes, FEDERAL_CODE]:
        region = get_region(code)
        if region.code in seen:
            continue
        seen.add(region.code)
        sources.append(
            SourceDocumentV1(
                region=region.code,
                title=region.document_title,
                url=region.source_url,
                last_verified=region.last_verified,
            )
        )
    return sources
