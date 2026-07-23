"""Расшифровки нормативных актов для ответов пользователю."""

from __future__ import annotations

import re

# короткие метки → полное официальное название
NPA_TITLES: dict[str, str] = {
    "СП 42.13330.2016": (
        'СП 42.13330.2016 «Градостроительство. Планировка и застройка '
        'городских и сельских поселений»'
    ),
    "СП 42.13330": (
        'СП 42.13330.2016 «Градостроительство. Планировка и застройка '
        'городских и сельских поселений»'
    ),
    "123-ФЗ": (
        "Федеральный закон от 22.07.2008 № 123-ФЗ "
        "«Технический регламент о требованиях пожарной безопасности»"
    ),
    "СанПиН 2.2.1/2.1.1.1200-03": (
        "СанПиН 2.2.1/2.1.1.1200-03 «Санитарно-защитные зоны и санитарная "
        "классификация предприятий, сооружений и иных объектов»"
    ),
    "СанПиН": (
        "СанПиН 2.2.1/2.1.1.1200-03 «Санитарно-защитные зоны и санитарная "
        "классификация предприятий, сооружений и иных объектов»"
    ),
}


def expand_npa_label(short_label: str) -> str:
    """Вернуть полное название НПА или исходную метку."""
    cleaned = (short_label or "").strip()
    if cleaned in NPA_TITLES:
        return NPA_TITLES[cleaned]
    for key, full in NPA_TITLES.items():
        if key.lower() in cleaned.lower():
            return full
    return cleaned


def federal_sp42_label() -> str:
    return NPA_TITLES["СП 42.13330.2016"]


_NPA_NUM_RE = re.compile(
    r"(?P<kind>Постановление|Приказ|СП)\b.*?N\s*(?P<num>[\w\-/\.]+)",
    re.IGNORECASE | re.DOTALL,
)


def short_npa_cite(document_title: str) -> str:
    """Краткая ссылка на НПА для цитат в ответе: «Приказ №78», «Постановление №713/30»."""
    title = (document_title or "").strip()
    match = _NPA_NUM_RE.search(title)
    if match:
        kind = match.group("kind")
        # нормализуем регистр вида документа
        kind_norm = kind[:1].upper() + kind[1:].lower() if kind else kind
        if kind.lower() == "сп":
            kind_norm = "СП"
        return f"{kind_norm} №{match.group('num')}"
    # федеральный СП без «N …»
    if "СП 42" in title:
        return "СП 42.13330.2016"
    head = title.split('"')[0].strip().rstrip(",")
    return head[:90] if head else "НПА"


def short_federal_cite_from_citation(citation: str) -> str:
    """По номеру пункта определить краткое имя федерального НПА."""
    cleaned = (citation or "").strip()
    lowered = cleaned.lower()
    if "123" in cleaned or "фз" in lowered:
        return "123-ФЗ"
    if "санпин" in lowered or "sanpin" in lowered:
        return "СанПиН 2.2.1/2.1.1.1200-03"
    return "СП 42.13330.2016"


def full_federal_cite_from_citation(citation: str) -> str:
    """Полное официальное название федерального НПА по citation."""
    return expand_npa_label(short_federal_cite_from_citation(citation))


# Справочные URL первоисточников (федеральный слой); региональные — из regions.yaml
FEDERAL_SOURCE_URLS: dict[str, str] = {
    "СП 42.13330.2016": (
        "https://meganorm.ru/mega_doc/norm/normy/0/"
        "sp_42_13330_2016_svod_pravil_gradostroitelstvo_planirovka_i.html"
    ),
    "123-ФЗ": "https://www.consultant.ru/document/cons_doc_LAW_78699/",
    "СанПиН 2.2.1/2.1.1.1200-03": (
        "https://www.consultant.ru/document/cons_doc_LAW_120401/"
    ),
}


def federal_source_url(citation: str) -> str:
    short = short_federal_cite_from_citation(citation)
    return FEDERAL_SOURCE_URLS.get(short, FEDERAL_SOURCE_URLS["СП 42.13330.2016"])

