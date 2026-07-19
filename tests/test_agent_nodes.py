from __future__ import annotations

from app.agent import nodes
from app.llm.base import LLMProviderError
from app.llm.schemas import ComparisonResult, DifferenceItem, ExtractionResult, RequirementItem


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


def test_normalize_business_type_skips_llm_for_short_phrase(monkeypatch) -> None:
    def _fail_if_called():
        raise AssertionError("для короткой фразы LLM вызывать не нужно")

    monkeypatch.setattr(nodes, "get_llm_provider", _fail_if_called)

    state = nodes.normalize_business_type({"business_type": "автомойка"})
    assert state == {"business_type": "автомойка"}


class _FakeProvider:
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> str:
        return self._response


def test_normalize_business_type_extracts_short_form_via_llm(monkeypatch) -> None:
    monkeypatch.setattr(nodes, "get_llm_provider", lambda: _FakeProvider("«склад»"))
    raw_text = "хочу построить склад в Краснодаре, у меня уже есть такой в московской области"

    state = nodes.normalize_business_type({"business_type": raw_text})

    assert state["business_type"] == "склад"
    assert state["business_type_raw"] == raw_text


def test_normalize_business_type_falls_back_to_raw_text_on_llm_error(monkeypatch) -> None:
    def _raise_provider_error():
        raise LLMProviderError("сервис недоступен")

    monkeypatch.setattr(nodes, "get_llm_provider", _raise_provider_error)
    raw_text = "хочу построить склад в Краснодаре, у меня уже есть такой в московской области"

    state = nodes.normalize_business_type({"business_type": raw_text})
    assert state == {"business_type": raw_text}


def test_esc_escapes_html_special_characters() -> None:
    assert nodes._esc("высота < 50 м & ширина") == "высота &lt; 50 м &amp; ширина"


def test_category_label_uses_friendly_names_with_fallback() -> None:
    assert nodes._category_label("сроки") == "⏱ Сроки"
    assert nodes._category_label("непонятная_категория") == "Непонятная категория"


def test_group_by_category_groups_items_by_category() -> None:
    items = [
        RequirementItem(category="сроки", description="a", citation="1"),
        RequirementItem(category="документы", description="b", citation="2"),
        RequirementItem(category="сроки", description="c", citation="3"),
    ]
    groups = nodes._group_by_category(items)
    assert len(groups["сроки"]) == 2
    assert len(groups["документы"]) == 1


def test_greeting_for_info_mentions_business_and_region() -> None:
    greeting = nodes._greeting_for_info("склад", "Московская область")
    assert "«склад»" in greeting
    assert "Московская область" in greeting
    assert "Я вас понял!" in greeting


def test_greeting_for_comparison_mentions_business_and_both_regions() -> None:
    greeting = nodes._greeting_for_comparison("склад", "Московская область", "Краснодарский край")
    assert "«склад»" in greeting
    assert "Московская область" in greeting
    assert "Краснодарский край" in greeting


def test_render_extraction_includes_greeting_regulator_category_and_citation() -> None:
    extraction = ExtractionResult(
        region_code="moscow_oblast",
        business_type="склад",
        items=[RequirementItem(category="сроки", description="Срок выдачи — 10 дней.", citation="3.2")],
    )
    text = nodes._render_extraction(extraction)

    assert "Я вас понял!" in text
    assert "«склад»" in text
    assert "Регулируется" in text
    assert "⏱ Сроки" in text
    assert "п. 3.2" in text


def test_citation_suffix_marks_federal_source_explicitly() -> None:
    assert nodes._citation_suffix("3.2", "региональный") == "(п. 3.2)"
    assert nodes._citation_suffix("5.1", "федеральный") == "(СП 42.13330.2016, п. 5.1)"


def test_render_extraction_marks_federal_fallback_item() -> None:
    # регион молчит по вопросу, но в федеральном СП нашлась применимая норма —
    # это лучше, чем оставить категорию пустой, но источник нужно явно назвать
    extraction = ExtractionResult(
        region_code="moscow_oblast",
        business_type="склад",
        items=[
            RequirementItem(
                category="сроки",
                description="Срок выдачи разрешения — 10 дней.",
                citation="5.1",
                is_specific=False,
                source_level="федеральный",
            )
        ],
    )
    text = nodes._render_extraction(extraction)

    assert "СП 42.13330.2016, п. 5.1" in text


def test_render_extraction_flags_general_norms_when_no_specific_ones_found() -> None:
    # склад буквально не упомянут в норме, но норма всё равно применима —
    # раньше в этом случае категория просто пропадала из ответа
    extraction = ExtractionResult(
        region_code="moscow_oblast",
        business_type="склад",
        items=[
            RequirementItem(
                category="сроки",
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
            RequirementItem(category="сроки", description="Спец. норма про склады.", citation="1.1", is_specific=True),
            RequirementItem(category="сроки", description="Общая норма про сроки.", citation="1.2", is_specific=False),
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
        differences=[
            DifferenceItem(
                category="сроки",
                region_a_value="10 дней",
                region_b_value="15 дней",
                summary="Срок выдачи отличается",
            )
        ],
    )
    text = nodes._render_comparison(comparison)

    assert "Требования почти совпадают" in text
    assert "10 дней" in text
    assert "15 дней" in text


def test_render_comparison_flags_general_norms_when_no_specific_ones_found() -> None:
    comparison = ComparisonResult(
        region_a="moscow_oblast",
        region_b="krasnodar_krai",
        business_type="склад",
        overall_summary="Есть отличие в общих сроках.",
        differences=[
            DifferenceItem(
                category="сроки",
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


def test_format_response_appends_disclaimer_on_success() -> None:
    state = {
        "mode": "info",
        "extraction": ExtractionResult(region_code="moscow_oblast", business_type="склад", items=[]),
    }
    result = nodes.format_response(state)
    assert "учусь" in result["response_text"]


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
