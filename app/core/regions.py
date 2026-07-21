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
    name_locative: str  # «в Краснодарском крае»
    document_title: str
    source_url: str
    local_raw_filename: str
    fetch_format: str  # "html" | "pdf" | "docx"
    last_verified: str  # дата ручной проверки, что акт ещё действует


def _doc_from_mapping(code: str, data: dict) -> RegionDocument:
    return RegionDocument(
        code=code,
        display_name=str(data["display_name"]).strip(),
        name_locative=str(data["name_locative"]).strip(),
        document_title=" ".join(str(data["document_title"]).split()),
        source_url=str(data["source_url"]).strip(),
        local_raw_filename=str(data["local_raw_filename"]).strip(),
        fetch_format=str(data["fetch_format"]).strip(),
        last_verified=str(data["last_verified"]).strip(),
    )


@lru_cache
def _load_config() -> tuple[dict[str, RegionDocument], RegionDocument]:
    with REGIONS_YAML.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    regions: dict[str, RegionDocument] = {}
    for code, data in (raw.get("regions") or {}).items():
        regions[code] = _doc_from_mapping(code, data)

    federal_raw = raw["federal"]
    federal_code = str(federal_raw.get("code", "federal"))
    federal = _doc_from_mapping(federal_code, federal_raw)
    return regions, federal


FEDERAL_CODE = "federal"

REGIONS: dict[str, RegionDocument]
FEDERAL_DOCUMENT: RegionDocument
REGIONS, FEDERAL_DOCUMENT = _load_config()
FEDERAL_CODE = FEDERAL_DOCUMENT.code


def get_region(code: str) -> RegionDocument:
    if code == FEDERAL_CODE:
        return FEDERAL_DOCUMENT
    if code not in REGIONS:
        raise ValueError(f"Неизвестный код региона: {code!r}. Доступны: {list(REGIONS)}")
    return REGIONS[code]


def region_choices() -> list[tuple[str, str]]:
    return [(region.code, region.display_name) for region in REGIONS.values()]


def all_documents() -> dict[str, RegionDocument]:
    """REGIONS + федеральный документ (для ingestion)."""
    return {**REGIONS, FEDERAL_CODE: FEDERAL_DOCUMENT}


def reload_regions() -> None:
    """Сброс кэша конфига (тесты / hot-reload админки)."""
    _load_config.cache_clear()
    global REGIONS, FEDERAL_DOCUMENT, FEDERAL_CODE
    REGIONS, FEDERAL_DOCUMENT = _load_config()
    FEDERAL_CODE = FEDERAL_DOCUMENT.code
