"""Загрузка object → categories для multi-query retrieval."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "object_categories.yaml"

ObjectTier = Literal["group1", "group2"]


@lru_cache
def _load() -> dict:
    with _CONFIG.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _match_key(key: str, mapping: dict) -> str | None:
    """Точное совпадение или подстрока ключа в mapping."""
    if key in mapping:
        return key
    for obj in mapping:
        if obj in key or key in obj:
            return obj
    return None


def categories_for_object(business_type: str) -> list[str]:
    data = _load()
    key = (business_type or "").strip().lower()
    mapping = data.get("objects") or {}
    matched = _match_key(key, mapping)
    if matched is not None:
        return list(mapping[matched])
    return list(data.get("defaults") or ["general"])


def tier_for_object(business_type: str) -> ObjectTier:
    """group1 — профильные объекты РНГП; group2 — рамочная коммерция."""
    data = _load()
    key = (business_type or "").strip().lower()
    tiers = data.get("object_tiers") or {}
    matched = _match_key(key, tiers)
    if matched is not None:
        raw = str(tiers[matched]).strip().lower()
        if raw in {"group1", "group2"}:
            return raw  # type: ignore[return-value]
    # эвристика по известным профильным корням, если нет в yaml
    profile_markers = (
        "детский сад",
        "школ",
        "многоквартир",
        "жилой дом",
        "мкд",
        "поликлиник",
        "больниц",
        "спорт",
        "стадион",
    )
    if any(m in key for m in profile_markers):
        return "group1"
    return "group2"


def query_phrases_for_object(
    business_type: str,
    *,
    tier: ObjectTier | None = None,
) -> list[str]:
    data = _load()
    cats = categories_for_object(business_type)
    qmap = data.get("category_queries") or {}
    key = (business_type or "").strip().lower()
    extras_map = data.get("object_query_extras") or {}
    extras = list(extras_map.get(key) or [])
    if not extras:
        matched = _match_key(key, extras_map)
        if matched is not None:
            extras = list(extras_map[matched])
    use_tier = tier or tier_for_object(key)
    if use_tier == "group1":
        extras = [*extras, *list(data.get("group1_query_extras") or [])]
    # тип → extras (формулировки юриста) → оси категорий
    phrases = [business_type, *extras, *[f"{business_type} {qmap.get(c, c)}" for c in cats]]
    seen: set[str] = set()
    out: list[str] = []
    for p in phrases:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out
