"""Загрузка object → categories для multi-query retrieval."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "object_categories.yaml"


@lru_cache
def _load() -> dict:
    with _CONFIG.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def categories_for_object(business_type: str) -> list[str]:
    data = _load()
    key = (business_type or "").strip().lower()
    mapping = data.get("objects") or {}
    if key in mapping:
        return list(mapping[key])
    for obj, cats in mapping.items():
        if obj in key or key in obj:
            return list(cats)
    return list(data.get("defaults") or ["general"])


def query_phrases_for_object(business_type: str) -> list[str]:
    data = _load()
    cats = categories_for_object(business_type)
    qmap = data.get("category_queries") or {}
    key = (business_type or "").strip().lower()
    extras_map = data.get("object_query_extras") or {}
    extras = list(extras_map.get(key) or [])
    if not extras:
        for obj, vals in extras_map.items():
            if obj in key or key in obj:
                extras = list(vals)
                break
    # тип → extras (формулировки юриста) → оси категорий
    phrases = [business_type, *extras, *[f"{business_type} {qmap.get(c, c)}" for c in cats]]
    seen: set[str] = set()
    out: list[str] = []
    for p in phrases:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out
