from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent.parent
REGIONS_YAML = BASE_DIR / "config" / "regions.yaml"


@dataclass(frozen=True)
class RegionDocument:
    code: str
    display_name: str
    name_locative: str
    document_title: str
    source_url: str
    local_raw_filename: str
    fetch_format: str
    last_verified: str
    aliases: tuple[str, ...] = ()


def _doc_from_mapping(code: str, data: dict) -> RegionDocument:
    aliases_raw = data.get("aliases") or []
    return RegionDocument(
        code=code,
        display_name=str(data["display_name"]).strip(),
        name_locative=str(data["name_locative"]).strip(),
        document_title=" ".join(str(data["document_title"]).split()),
        source_url=str(data.get("source_url") or "").strip(),
        local_raw_filename=str(data["local_raw_filename"]).strip(),
        fetch_format=str(data["fetch_format"]).strip(),
        last_verified=str(data["last_verified"]).strip(),
        aliases=tuple(str(a).strip() for a in aliases_raw if str(a).strip()),
    )


@lru_cache
def _load_config() -> tuple[dict[str, RegionDocument], RegionDocument, dict[str, str]]:
    with REGIONS_YAML.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    regions: dict[str, RegionDocument] = {}
    alias_to_code: dict[str, str] = {}
    for code, data in (raw.get("regions") or {}).items():
        doc = _doc_from_mapping(code, data)
        regions[code] = doc
        alias_to_code[code.lower()] = code
        for alias in doc.aliases:
            alias_to_code[alias.lower()] = code

    federal_raw = raw["federal"]
    federal_code = str(federal_raw.get("code", "RU-FED"))
    federal = _doc_from_mapping(federal_code, federal_raw)
    alias_to_code[federal_code.lower()] = federal_code
    for alias in federal.aliases:
        alias_to_code[alias.lower()] = federal_code

    return regions, federal, alias_to_code


FEDERAL_CODE = "RU-FED"

REGIONS: dict[str, RegionDocument]
FEDERAL_DOCUMENT: RegionDocument
_ALIAS_MAP: dict[str, str]
REGIONS, FEDERAL_DOCUMENT, _ALIAS_MAP = _load_config()
FEDERAL_CODE = FEDERAL_DOCUMENT.code


def resolve_region_code(code: str) -> str:
    """Приводит ISO или legacy-алиас к каноническому коду."""
    key = (code or "").strip()
    if not key:
        raise ValueError("пустой код региона")
    resolved = _ALIAS_MAP.get(key.lower())
    if resolved is None:
        raise ValueError(f"Неизвестный код региона: {code!r}. Доступны: {list(REGIONS)} / aliases")
    return resolved


def get_region(code: str) -> RegionDocument:
    resolved = resolve_region_code(code)
    if resolved == FEDERAL_CODE:
        return FEDERAL_DOCUMENT
    return REGIONS[resolved]


def region_choices() -> list[tuple[str, str]]:
    return [(region.code, region.display_name) for region in REGIONS.values()]


def all_documents() -> dict[str, RegionDocument]:
    """REGIONS + федеральный документ (для ingestion)."""
    return {**REGIONS, FEDERAL_CODE: FEDERAL_DOCUMENT}


def reload_regions() -> None:
    """Сброс кэша конфига (тесты / hot-reload админки)."""
    _load_config.cache_clear()
    global REGIONS, FEDERAL_DOCUMENT, FEDERAL_CODE, _ALIAS_MAP
    REGIONS, FEDERAL_DOCUMENT, _ALIAS_MAP = _load_config()
    FEDERAL_CODE = FEDERAL_DOCUMENT.code
