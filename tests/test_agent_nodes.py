from __future__ import annotations

from app.agent import nodes
from app.core.business_type import contains_forbidden_words, is_known_business_type, looks_like_business_query
from app.llm.base import LLMProviderError
from app.llm.schemas import (
    CommonRequirementItem,
    ComparisonResult,
    DifferenceItem,
    ExtractionResult,
    RequirementItem,
)
from app.vectorstore.types import RetrievedChunk


def test_understand_query_requires_business_type() -> None:
    state = nodes.understand_query({"business_type": "", "region_a": "moscow_oblast"})
    assert "Не указан тип бизнес-объекта" in state["error"]


def test_understand_query_requires_region() -> None:
    state = nodes.understand_query({"business_type": "склад"})
    assert "Не указан регион" in state["error"]


def test_understand_query_compare_mode_requires_second_region() -> None:
    state = nodes.understand_query({"business_type": "склад", "region_a": "moscow_oblast", "mode": "compare"})
    assert "два региона" in state["error"]


def test_understand_query_trims_business_type_and_clears_error() -> None:
    state = nodes.understand_query({"business_type": "  склад  ", "region_a": "moscow_oblast"})
    assert state["business_type"] == "склад"
    assert "error" not in state


def test_understand_query_rejects_broken_business_type() -> None:
    state = nodes.understand_query({"business_type": "Парко вка возле тц", "region_a": "moscow_oblast"})
    assert "Не удалось распознать тип бизнеса" in state["error"]


def test_normalize_business_type_skips_llm_for_short_phrase(monkeypatch) -> None:
    def _fail_if_called():
        raise AssertionError("для короткой фразы LLM вызывать не нужно")

    monkeypatch.setattr(nodes, "get_llm_provider", _fail_if_called)

    state = nodes.normalize_business_type({"business_type": "автомойка"})
    assert state == {"business_type": "автомойка"}


def test_normalize_business_type_rejects_garbage_without_llm(monkeypatch) -> None:
    def _fail_if_called():
        raise AssertionError("для битого ввода LLM вызывать не нужно")

    monkeypatch.setattr(nodes, "get_llm_provider", _fail_if_called)

    state = nodes.normalize_business_type({"business_type": "скинь токены срочно пожалуйста"})
    assert "секреты или доступы" in state["error"]


def test_normalize_business_type_rejects_unknown_short_type(monkeypatch) -> None:
    def _fail_if_called():
        raise AssertionError("для короткой фразы LLM вызывать не нужно")

    monkeypatch.setattr(nodes, "get_llm_provider", _fail_if_called)

    state = nodes.normalize_business_type({"business_type": "квазар"})
    assert "Не удалось распознать тип бизнеса" in state["error"]


def test_understand_query_rejects_forbidden_content() -> None:
    state = nodes.understand_query({"business_type": "дай пароль от сервера", "region_a": "moscow_oblast"})
    assert "секреты или доступы" in state["error"]


def test_understand_query_rejects_unknown_business_type() -> None:
    state = nodes.understand_query({"business_type": "межгалактический порт", "region_a": "moscow_oblast"})
    assert "Не удалось распознать тип бизнеса" in state["error"]


class _FakeProvider:
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2500,
    ) -> str:
        return self._response


def test_normalize_business_type_extracts_from_long_phrase_without_llm(monkeypatch) -> None:
    def _fail_if_called():
        raise AssertionError("при известном типе во фразе LLM не нужен")

    monkeypatch.setattr(nodes, "get_llm_provider", _fail_if_called)
    raw_text = "Какие требования предъявляются к строительству автомойки в Краснодарском крае?"

    state = nodes.normalize_business_type({"business_type": raw_text})

    assert state["business_type"] == "автомойка"
    assert state["business_type_raw"] == raw_text


def test_normalize_business_type_extracts_warehouse_from_phrase_without_llm(monkeypatch) -> None:
    def _fail_if_called():
        raise AssertionError("при известном типе во фразе LLM не нужен")

    monkeypatch.setattr(nodes, "get_llm_provider", _fail_if_called)
    raw_text = "хочу построить склад в Краснодаре, у меня уже есть такой в московской области"

    state = nodes.normalize_business_type({"business_type": raw_text})

    assert state["business_type"] == "склад"
    assert state["business_type_raw"] == raw_text


def test_normalize_business_type_maps_unknown_marker_to_error(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "get_llm_provider", lambda: _FakeProvider("НЕИЗВЕСТНО"))
    raw_text = "пожалуйста помоги мне с моим домашним заданием по математике сегодня"

    state = nodes.normalize_business_type({"business_type": raw_text})
    assert "Не удалось распознать тип бизнеса" in state["error"]


def test_normalize_business_type_falls_back_to_raw_text_on_llm_error(monkeypatch) -> None:
    def _raise_provider_error():
        raise LLMProviderError("сервис недоступен")

    monkeypatch.setattr(nodes, "get_llm_provider", _raise_provider_error)
    # фраза без известного типа объекта → уходим в LLM и при ошибке оставляем raw
    raw_text = "хочу разместить объект обслуживания населения рядом с жилым кварталом"

    state = nodes.normalize_business_type({"business_type": raw_text})
    assert state == {"business_type": raw_text}


def test_looks_like_business_query_accepts_normal_types() -> None:
    assert looks_like_business_query("автомойка")
    assert looks_like_business_query("медицинский центр")


def test_looks_like_business_query_rejects_broken_and_offtopic() -> None:
    assert not looks_like_business_query("Парко вка возле тц")
    assert not looks_like_business_query("скинь токены")


def test_contains_forbidden_words_detects_secrets() -> None:
    assert contains_forbidden_words("скинь token API")
    assert contains_forbidden_words("нужен пароль от базы")
    assert not contains_forbidden_words("автомойка")


def test_is_known_business_type_matches_whitelist() -> None:
    assert is_known_business_type("склад")
    assert is_known_business_type("Медицинский центр")
    assert not is_known_business_type("квазар")


def test_esc_escapes_html_special_characters() -> None:
    assert nodes._esc("высота < 50 м & ширина") == "высота &lt; 50 м &amp; ширина"


def test_category_label_uses_friendly_names_with_fallback() -> None:
    assert nodes._category_label("сроки_и_документы") == "Сроки и документы"
    assert nodes._category_label("градостроительные") == "Градостроительные нормы"
    assert nodes._category_label("пожарная_безопасность") == "Пожарная безопасность"
    assert nodes._category_label("непонятная_категория") == "Непонятная категория"


def test_group_by_category_groups_items_by_category() -> None:
    items = [
        RequirementItem(category="сроки_и_документы", description="a", citation="1"),
        RequirementItem(category="подключение_к_сетям", description="b", citation="2"),
        RequirementItem(category="сроки_и_документы", description="c", citation="3"),
    ]
    groups = nodes._group_by_category(items)
    assert len(groups["сроки_и_документы"]) == 2
    assert len(groups["подключение_к_сетям"]) == 1


def test_greeting_for_info_mentions_business_and_region() -> None:
    greeting = nodes._greeting_for_info("склад", "Московской области")
    assert "«склад»" in greeting
    assert "Московской области" in greeting
    assert "Требования к объекту капитального строительства" in greeting


def test_greeting_for_comparison_mentions_business_and_both_regions() -> None:
    greeting = nodes._greeting_for_comparison("склад", "Московской области", "Краснодарском крае")
    assert "«склад»" in greeting
    assert "в Московской области" in greeting
    assert "в Краснодарском крае" in greeting
    assert "Сравнение требований" in greeting


def test_render_extraction_includes_greeting_regulator_category_and_citation() -> None:
    extraction = ExtractionResult(
        region_code="moscow_oblast",
        business_type="склад",
        items=[
            RequirementItem(
                category="сроки_и_документы",
                description="Срок выдачи — 10 дней.",
                citation="3.2",
            )
        ],
    )
    text = nodes._render_extraction(extraction)

    assert "Требования к объекту капитального строительства" in text
    assert "«склад»" in text
    assert "в Московской области" in text
    assert "Правовое регулирование (регион)" in text
    assert "Федеральный уровень" in text
    assert "Региональный уровень" in text
    assert "Наличие требований по объекту" in text
    assert "Сроки и документы" in text
    assert "п. 3.2" in text
    assert "713/30" in text
    assert "открыть первоисточник" in text
    assert "По остальным категориям данные не найдены" not in text
    assert "Что требуется проверить дополнительно" in text
    assert "только учусь" not in text  # дисклеймер в format_response
    assert "объекту капитального строительства" in text
    assert "региональный:" in text


def test_audit_sections_from_state_dedupes_chunks() -> None:
    from app.vectorstore.types import RetrievedChunk

    chunk = RetrievedChunk(
        id="c1",
        text="x",
        region_code="krasnodar_krai",
        section_number="5.5.153",
        category=None,
        distance=0.1,
    )
    rows = nodes.audit_sections_from_state(
        {"retrieved_a": [chunk], "retrieved_federal": [chunk]}
    )
    assert len(rows) == 1
    assert rows[0]["section_number"] == "5.5.153"


def test_citation_suffix_marks_federal_source_explicitly() -> None:
    assert nodes._citation_suffix("3.2", "региональный") == "(п. 3.2)"
    federal = nodes._citation_suffix("5.1", "федеральный")
    assert "СП 42.13330.2016" in federal
    assert "п. 5.1" in federal


def test_citation_suffix_strips_punkt_noise() -> None:
    assert nodes._citation_suffix("пункт 725", "региональный") == "(п. 725)"
    assert nodes._citation_suffix("п. 5.23", "региональный") == "(п. 5.23)"


def test_render_extraction_marks_federal_fallback_item() -> None:
    extraction = ExtractionResult(
        region_code="moscow_oblast",
        business_type="склад",
        items=[
            RequirementItem(
                category="сроки_и_документы",
                description="Срок выдачи разрешения — 10 дней.",
                citation="5.1",
                is_specific=False,
                source_level="федеральный",
            )
        ],
    )
    text = nodes._render_extraction(extraction)

    assert "СП 42.13330.2016" in text or "п. 5.1" in text
    assert "Региональный уровень" in text
    assert "не установлены" in text
    assert "применяются федеральные" in text
    assert "Федеральный уровень" in text


def test_render_extraction_flags_general_norms_when_no_specific_ones_found() -> None:
    extraction = ExtractionResult(
        region_code="moscow_oblast",
        business_type="склад",
        items=[
            RequirementItem(
                category="сроки_и_документы",
                description="Срок выдачи разрешения — 10 дней.",
                citation="3.2",
                is_specific=False,
            )
        ],
    )
    text = nodes._render_extraction(extraction)

    assert "Специальных требований" in text
    assert "общие нормы" in text
    assert "Срок выдачи разрешения" in text


def test_render_extraction_shows_specific_and_general_separately() -> None:
    extraction = ExtractionResult(
        region_code="moscow_oblast",
        business_type="склад",
        items=[
            RequirementItem(
                category="сроки_и_документы",
                description="Спец. норма про склады.",
                citation="1.1",
                is_specific=True,
            ),
            RequirementItem(
                category="сроки_и_документы",
                description="Общая норма про сроки.",
                citation="1.2",
                is_specific=False,
            ),
        ],
    )
    text = nodes._render_extraction(extraction)

    assert "Спец. норма про склады" in text
    assert "Плюс действуют общие нормы" in text
    assert "Общая норма про сроки" in text


def test_render_comparison_includes_summary_and_both_regions() -> None:
    comparison = ComparisonResult(
        region_a="moscow_oblast",
        region_b="krasnodar_krai",
        business_type="склад",
        overall_summary="Требования почти совпадают.",
        common_requirements=[
            CommonRequirementItem(
                category="градостроительные",
                description="Парковки считаются по общим правилам регионального норматива.",
                citation="5.1",
            )
        ],
        differences=[
            DifferenceItem(
                category="сроки_и_документы",
                region_a_value="10 дней",
                region_b_value="15 дней",
                summary="Срок выдачи отличается",
                citation_a="3.2",
                citation_b="4.1",
            )
        ],
    )
    text = nodes._render_comparison(comparison)

    assert "Требования почти совпадают" in text
    assert "в Московской области" in text
    assert "в Краснодарском крае" in text
    assert "Что совпадает" in text
    assert "Чем отличаются" in text
    # различия идут раньше совпадений
    assert text.index("Чем отличаются") < text.index("Что совпадает")
    assert "1. Парковки" in text
    assert "1. Срок выдачи отличается" in text
    assert "10 дней" in text
    assert "15 дней" in text
    assert "🔹" in text
    assert "🔸" in text
    assert "(МО)" not in text
    assert "(КК)" not in text
    assert "Постановление" in text and "713/30" in text
    assert "Приказ" in text and "78" in text
    assert "п. 3.2" in text
    assert "п. 4.1" in text
    assert "Как читать сравнение" in text
    assert "первоисточник" in text
    assert "🔵" not in text
    assert "🟢" not in text
    assert "Что требуется проверить дополнительно" in text


def test_render_comparison_uses_correct_npa_titles_for_each_region() -> None:
    comparison = ComparisonResult(
        region_a="moscow_oblast",
        region_b="krasnodar_krai",
        business_type="автосервис",
        overall_summary="Есть отличия.",
        differences=[],
    )
    text = nodes._render_comparison(comparison)

    assert "N 713/30" in text
    assert "N 78" in text
    assert text.index("N 713/30") < text.index("N 78")
    assert "Различий не обнаружено" in text
    assert "🏛" in text
    assert "⚖" in text
    assert "📜" in text
    assert "🗺" not in text


def test_render_comparison_humanizes_missing_fragment_phrase() -> None:
    comparison = ComparisonResult(
        region_a="moscow_oblast",
        region_b="krasnodar_krai",
        business_type="склад",
        overall_summary="Отличие есть.",
        differences=[
            DifferenceItem(
                category="сроки_и_документы",
                region_a_value="не найдено в предоставленных фрагментах",
                region_b_value="10 дней",
                summary="Срок отличается",
                citation_a="",
                citation_b="4.1",
            )
        ],
    )
    text = nodes._render_comparison(comparison)

    assert "предоставленных фрагментах" not in text
    assert (
        "региональные требования отсутствуют" in text
        or "в нормативе региона не указано" in text
    )
    assert "номер пункта в доступных фрагментах не приведён" in text


def test_render_comparison_flags_general_norms_when_no_specific_ones_found() -> None:
    comparison = ComparisonResult(
        region_a="moscow_oblast",
        region_b="krasnodar_krai",
        business_type="склад",
        overall_summary="Есть отличие в общих сроках.",
        differences=[
            DifferenceItem(
                category="сроки_и_документы",
                region_a_value="10 дней",
                region_b_value="15 дней",
                summary="Срок выдачи отличается",
                is_specific=False,
                citation_a="1.1",
                citation_b="1.2",
            )
        ],
    )
    text = nodes._render_comparison(comparison)

    assert "Специальных норм" in text
    assert "общие требования" in text


def test_citation_matches_chunks_accepts_known_section() -> None:
    chunks = [
        RetrievedChunk(
            id="1",
            text="норма",
            region_code="moscow_oblast",
            section_number="5.5.153",
            category=None,
            distance=0.1,
        )
    ]
    assert nodes._citation_matches_chunks("5.5.153", chunks)
    assert nodes._citation_matches_chunks("п. 5.5.153", chunks)
    assert not nodes._citation_matches_chunks("725", chunks)


def test_chunk_mentions_business_handles_carwash_morphology() -> None:
    chunk = RetrievedChunk(
        id="1",
        text="Станции технического обслуживания, автомойки | 1 бокс | 1",
        region_code="krasnodar_krai",
        section_number="табл.108",
        category=None,
        distance=0.1,
    )
    assert nodes._chunk_mentions_business(chunk, "автомойка")
    assert not nodes._chunk_mentions_business(chunk, "склад")


def test_section_rank_quality_prefers_dotted_over_table_junk() -> None:
    assert nodes._section_rank_quality("5.5.153") > nodes._section_rank_quality("1")
    assert nodes._section_rank_quality("табл.108") > nodes._section_rank_quality("300")
    assert nodes._section_rank_quality("СанПиН/7.1.3") >= nodes._section_rank_quality("5.5.153")
    assert nodes._section_rank_quality("НО-доп/2") > nodes._section_rank_quality("1/е")
    assert nodes._section_rank_quality("а/в") == 0
    assert nodes._section_rank_quality("табл.108") > nodes._section_rank_quality("табл.p104.1")


def test_type_affinity_prefers_matching_curated_tags() -> None:
    azs = RetrievedChunk(
        id="curated::RU-FED::СанПиН/7.1.5",
        text="АЗС СЗЗ 100 м",
        region_code="RU-FED",
        section_number="СанПиН/7.1.5",
        category=None,
        distance=0.2,
        tags=["азс"],
        doc_type="CURATED",
    )
    warehouse = RetrievedChunk(
        id="curated::RU-MOS::МО-доп/склад",
        text="складские объекты",
        region_code="RU-MOS",
        section_number="МО-доп/склад",
        category=None,
        distance=0.05,
        tags=["склад"],
        doc_type="CURATED",
    )
    generic = RetrievedChunk(
        id="curated::RU-FED::СанПиН/2.1",
        text="определение СЗЗ",
        region_code="RU-FED",
        section_number="СанПиН/2.1",
        category=None,
        distance=0.01,
        tags=["азс", "склад", "торговый центр"],
        doc_type="CURATED",
    )
    assert nodes._type_affinity(azs, "азс") > nodes._type_affinity(warehouse, "азс")
    assert nodes._type_affinity(azs, "азс") > nodes._type_affinity(generic, "азс")


def test_weak_retrieval_support_refuses_sparse_noise() -> None:
    junk = [
        RetrievedChunk(
            id="j1",
            text="общий текст без опоры",
            region_code="RU-FED",
            section_number="8.125",
            category=None,
            distance=0.3,
        )
    ]
    assert nodes._weak_retrieval_support(junk, [], [])
    curated = [
        RetrievedChunk(
            id="curated::RU-FED::СанПиН/7.1.5",
            text="АЗС СЗЗ",
            region_code="RU-FED",
            section_number="СанПиН/7.1.5",
            category=None,
            distance=0.1,
            tags=["азс"],
            doc_type="CURATED",
        ),
        RetrievedChunk(
            id="c2",
            text="ещё фрагмент",
            region_code="RU-FED",
            section_number="12.4.4",
            category=None,
            distance=0.2,
        ),
    ]
    assert not nodes._weak_retrieval_support([], curated, [])


def test_resolve_retrieval_type_from_paraphrase() -> None:
    assert nodes._resolve_retrieval_type("цех металлообработки") == "производство"
    assert nodes._resolve_retrieval_type("административное здание делового центра") == "офис"
    assert nodes._resolve_retrieval_type("ТРЦ с фудкортом") == "торговый центр"


def test_citation_rejects_prefix_against_ambiguous_section_one() -> None:
    """section_number='1' из таблиц не должен подтверждать выдуманные 1.x / 15."""
    chunks = [
        RetrievedChunk(
            id="t1",
            text="автомойки | 1 бокс",
            region_code="krasnodar_krai",
            section_number="1",
            category=None,
            distance=0.1,
        )
    ]
    assert nodes._citation_matches_chunks("1", chunks)
    assert not nodes._citation_matches_chunks("1.5.153", chunks)
    assert not nodes._citation_matches_chunks("15", chunks)
    assert not nodes._citation_matches_chunks("5.5.153", chunks)


def test_citation_matches_curated_federal_ids() -> None:
    chunks = [
        RetrievedChunk(
            id="f1",
            text="СЗЗ для автомоек",
            region_code="federal",
            section_number="СанПиН/7.1.3",
            category="санитарные_экологические",
            distance=0.1,
        ),
        RetrievedChunk(
            id="f2",
            text="пожарная безопасность",
            region_code="federal",
            section_number="123-ФЗ/6",
            category="пожарная_безопасность",
            distance=0.2,
        ),
    ]
    assert nodes._citation_matches_chunks("СанПиН/7.1.3", chunks)
    assert nodes._citation_matches_chunks("7.1.3", chunks)
    assert nodes._citation_matches_chunks("123-ФЗ/6", chunks)
    # голый «6» без префикса — слишком коротко, не матчим
    assert not nodes._citation_matches_chunks("6", chunks)


def test_filter_grounded_items_drops_hallucinated_citations() -> None:
    chunks = [
        RetrievedChunk(
            id="1",
            text="норма",
            region_code="sverdlovsk_oblast",
            section_number="1.2",
            category=None,
            distance=0.1,
        )
    ]
    items = [
        RequirementItem(category="сроки_и_документы", description="Реальное.", citation="1.2"),
        RequirementItem(category="сроки_и_документы", description="Выдумка.", citation="725"),
    ]
    grounded = nodes._filter_grounded_items(items, chunks)
    assert len(grounded) == 1
    assert grounded[0].citation == "1.2"


def test_replace_region_placeholders_uses_display_names() -> None:
    text = "Только в регионе А установлены требования; в регионе B их нет."
    cleaned = nodes._replace_region_placeholders(text, "Московская область", "Краснодарский край")
    assert "регионе А" not in cleaned
    assert "регионе B" not in cleaned
    assert "Московская область" in cleaned
    assert "Краснодарский край" in cleaned


def test_fuzzy_resolves_medical_typo() -> None:
    from app.core.business_type import fuzzy_match_business_type, resolve_business_type

    assert fuzzy_match_business_type("медьцынский центр") == "медицинский центр"
    assert resolve_business_type("Медьцынский центр") == "медицинский центр"


def test_normalize_business_type_fixes_typo_without_llm(monkeypatch) -> None:
    def _fail_if_called():
        raise AssertionError("для короткой фразы LLM вызывать не нужно")

    monkeypatch.setattr(nodes, "get_llm_provider", _fail_if_called)

    state = nodes.normalize_business_type({"business_type": "медьцынский центр"})
    assert state["business_type"] == "медицинский центр"


def test_format_response_appends_disclaimer_on_success() -> None:
    state = {
        "mode": "info",
        "extraction": ExtractionResult(region_code="moscow_oblast", business_type="склад", items=[]),
    }
    result = nodes.format_response(state)
    assert "Справочный помощник RegioBuild" in result["response_text"]
    assert "не является юридической консультацией" in result["response_text"]
    assert "муниципальном" in result["response_text"]


def test_format_response_shows_normalized_business_type_prefix() -> None:
    state = {
        "mode": "info",
        "business_type": "склад",
        "business_type_raw": "хочу построить склад в Краснодаре",
        "extraction": ExtractionResult(region_code="moscow_oblast", business_type="склад", items=[]),
    }
    result = nodes.format_response(state)
    assert "Тип объекта:" in result["response_text"]
    assert "«склад»" in result["response_text"]
    assert "Распознанный тип бизнеса" not in result["response_text"]


def test_format_response_escapes_error_message() -> None:
    state = {"error": "регион <неизвестен>"}
    result = nodes.format_response(state)
    assert "&lt;неизвестен&gt;" in result["response_text"]
