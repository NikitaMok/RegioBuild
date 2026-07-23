"""Узкие аспекты запроса: при отсутствии опоры в корпусе — честный отказ, не подмена темы."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.vectorstore.types import RetrievedChunk


@dataclass(frozen=True)
class QueryAspect:
    key: str
    label: str
    query_markers: tuple[str, ...]
    evidence_markers: tuple[str, ...]


# Если в запросе есть query_markers, в чанках должны встретиться evidence_markers.
ASPECTS: tuple[QueryAspect, ...] = (
    QueryAspect(
        key="plot_area",
        label="норм площади земельного участка / показателей обеспеченности по площади",
        query_markers=(
            "площад",
            "участк",
            "земельн",
            "процент застрой",
            "обеспеченност",
            "показател",
        ),
        # для plot_area проверяем отдельно — нужны числовые/площадные маркеры
        evidence_markers=(
            "га ",
            "га.",
            " м2",
            "м²",
            "кв.м",
            "кв м",
            "соток",
        ),
    ),
    QueryAspect(
        key="fire_distance",
        label="противопожарных расстояний",
        query_markers=("противопожарн", "пожарны", "разрывы", "расстояни"),
        evidence_markers=("противопожарн", "пожар", "разрыв", "расстоян", "123-фз", "123"),
    ),
)


def detect_aspects(text: str) -> list[QueryAspect]:
    lowered = (text or "").lower()
    if not lowered.strip():
        return []
    found: list[QueryAspect] = []
    for aspect in ASPECTS:
        # plot_area: «площадь участка» ИЛИ «нормы по участку» (без слова «площадь»)
        if aspect.key == "plot_area":
            has_area = "площад" in lowered
            has_plot = any(
                m in lowered for m in ("участк", "земельн", "обеспеченност", "показател")
            )
            norms_for_plot = ("участк" in lowered) and any(
                m in lowered for m in ("норм", "требован", "показател", "обеспеченност")
            )
            if (has_area and has_plot) or norms_for_plot:
                found.append(aspect)
            continue
        if aspect.key == "fire_distance":
            if "противопожарн" in lowered or (
                "пожар" in lowered and "расстоян" in lowered
            ):
                found.append(aspect)
            continue
        if any(m in lowered for m in aspect.query_markers):
            found.append(aspect)
    return found


def aspects_supported(aspects: list[QueryAspect], chunks: list[RetrievedChunk]) -> bool:
    if not aspects:
        return True
    corpus = "\n".join(
        f"{c.section_number or ''} {c.text or ''}" for c in chunks
    ).lower()
    if not corpus.strip():
        return False
    for aspect in aspects:
        if aspect.key == "plot_area":
            # одного упоминания «участок/СЗЗ» мало — нужны площадьные величины
            if any(m in corpus for m in aspect.evidence_markers):
                continue
            if ("обеспеченност" in corpus or "показател" in corpus) and re.search(
                r"\d+[.,]?\d*\s*(га|м2|м²|кв)", corpus
            ):
                continue
            return False
        if not any(m in corpus for m in aspect.evidence_markers):
            return False
    return True


def refusal_for_unsupported_aspects(
    aspects: list[QueryAspect],
    *,
    business_type: str,
    region_label: str,
) -> str:
    labels = "; ".join(a.label for a in aspects)
    obj = (business_type or "объекту").strip()
    region = (region_label or "выбранном субъекте РФ").strip()
    return (
        f"По вашему запросу конкретных {labels} для «{obj}» в {region} "
        f"в доступных региональных РНГП/ТСН и федеральном фоне не найдено. "
        f"Рекомендуем обратиться к муниципальным ПЗЗ, отраслевым НПА или "
        f"проектной документации."
    )
