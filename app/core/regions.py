from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegionDocument:
    code: str
    display_name: str
    document_title: str
    source_url: str
    local_raw_filename: str
    fetch_format: str  # "html" | "pdf" | "docx"
    last_verified: str  # дата ручной проверки, что акт ещё действует


REGIONS: dict[str, RegionDocument] = {
    "moscow_oblast": RegionDocument(
        code="moscow_oblast",
        display_name="Московская область",
        document_title=(
            "Постановление Правительства МО от 17.08.2015 N 713/30 "
            '"Об утверждении нормативов градостроительного проектирования Московской области"'
        ),
        source_url="https://meganorm.ru/mega_doc/dop1/84/postanovlenie_administratsii_gorodskogo_okruga_balashikha_mo/0/postanovlenie_pravitelstva_mo_ot_17_08_2015_N_713_30_red_ot.html",
        local_raw_filename="moscow_oblast_rngp.html",
        fetch_format="html",
        last_verified="2026-07-19",
    ),
    "krasnodar_krai": RegionDocument(
        code="krasnodar_krai",
        display_name="Краснодарский край",
        document_title=(
            "Приказ департамента по архитектуре и градостроительству Краснодарского края "
            'от 16.04.2015 N 78 "Об утверждении нормативов градостроительного проектирования '
            'Краснодарского края"'
        ),
        # docs.cntd.ru отдаёт документ кусками при скролле — берём .docx с admnvrsk.ru
        source_url="https://admnvrsk.ru/gorozhanam/gradostroitelnaya-deyatelnost/normativy-gradostroitelnogo-proektirovaniya/",
        local_raw_filename="krasnodar_krai_rngp.docx",
        fetch_format="docx",
        last_verified="2026-07-19",
    ),
    "sverdlovsk_oblast": RegionDocument(
        code="sverdlovsk_oblast",
        display_name="Свердловская область",
        document_title=(
            "Приказ Министерства строительства и развития инфраструктуры Свердловской "
            'области от 01.08.2023 N 435-П "Об утверждении региональных нормативов '
            'градостроительного проектирования Свердловской области"'
        ),
        # вместо утратившего силу 380-ПП от 2010 г.
        source_url="http://proj66.ru/6600.svo/%D0%9D%D0%93%D0%9F%D0%A1%D0%9E.htm",
        local_raw_filename="sverdlovsk_oblast_rngp.html",
        fetch_format="html",
        last_verified="2026-07-19",
    ),
    "novosibirsk_oblast": RegionDocument(
        code="novosibirsk_oblast",
        display_name="Новосибирская область",
        document_title=(
            "Постановление Правительства Новосибирской области от 12.08.2015 N 303-п "
            '"Об утверждении региональных нормативов градостроительного проектирования '
            'Новосибирской области" (с изменениями)'
        ),
        source_url="https://novosib-gov.ru/doc/90836",
        local_raw_filename="novosibirsk_oblast_rngp.html",
        fetch_format="html",
        last_verified="2026-07-19",
    ),
    "tatarstan": RegionDocument(
        code="tatarstan",
        display_name="Республика Татарстан",
        document_title=(
            "Постановление Кабинета Министров Республики Татарстан от 27.12.2013 N 1071 "
            '"Об утверждении республиканских нормативов градостроительного проектирования '
            'Республики Татарстан" (с изменениями)'
        ),
        source_url="https://meganorm.ru/Data2/1/4293726/4293726081.htm",
        local_raw_filename="tatarstan_rngp.html",
        fetch_format="html",
        last_verified="2026-07-19",
    ),
}


FEDERAL_CODE = "federal"

# Не в REGIONS: это фон для любого региона, а не пункт выбора в UI.
FEDERAL_DOCUMENT = RegionDocument(
    code=FEDERAL_CODE,
    display_name="Российская Федерация (федеральный уровень)",
    document_title=(
        'СП 42.13330.2016 "Градостроительство. Планировка и застройка городских '
        'и сельских поселений" (актуализированная редакция СНиП 2.07.01-89*)'
    ),
    source_url="https://meganorm.ru/mega_doc/norm/normy/0/sp_42_13330_2016_svod_pravil_gradostroitelstvo_planirovka_i.html",
    local_raw_filename="federal_sp42.html",
    fetch_format="html",
    last_verified="2026-07-19",
)


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
