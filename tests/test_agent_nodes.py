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
from app.vectorstore.retriever import RetrievedChunk


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


def test_normalize_business_type_extracts_short_form_via_llm(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "get_llm_provider", lambda: _FakeProvider("«склад»"))
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
    raw_text = "хочу построить склад в Краснодаре, у меня уже есть такой в московской области"

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
    assert "Я вас понял!" in greeting


def test_greeting_for_comparison_mentions_business_and_both_regions() -> None:
    greeting = nodes._greeting_for_comparison("склад", "Московской области", "Краснодарском крае")
    assert "«склад»" in greeting
    assert "в Московской области" in greeting
    assert "в Краснодарском крае" in greeting


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

    assert "Я вас понял!" in text
    assert "«склад»" in text
    assert "в Московской области" in text
    assert "Правовое регулирование" in text
    assert "Федеральные нормы (применяются при отсутствии региональных)" in text
    assert "Сроки и документы" in text
    assert "п. 3.2" in text
    assert "По остальным категориям данные не найдены" in text
    assert "Что требуется проверить дополнительно" in text
    assert "юридической консультацией" not in text  # дисклеймер в format_response


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

    assert "СП 42.13330.2016" in text
    assert "п. 5.1" in text
    assert "Специальных региональных норм нет" in text


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
    assert "🔵" in text
    assert "🟢" in text
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
            )
        ],
    )
    text = nodes._render_comparison(comparison)

    assert "предоставленных фрагментах" not in text
    assert (
        "региональные требования отсутствуют" in text
        or "в нормативе региона не указано" in text
    )


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
    assert "не является юридической консультацией" in result["response_text"]


def test_format_response_shows_normalized_business_type_prefix() -> None:
    state = {
        "mode": "info",
        "business_type": "склад",
        "business_type_raw": "хочу построить склад в Краснодаре",
        "extraction": ExtractionResult(region_code="moscow_oblast", business_type="склад", items=[]),
    }
    result = nodes.format_response(state)
    assert "Распознанный тип бизнеса" in result["response_text"]


def test_format_response_escapes_error_message() -> None:
    state = {"error": "регион <неизвестен>"}
    result = nodes.format_response(state)
    assert "&lt;неизвестен&gt;" in result["response_text"]
