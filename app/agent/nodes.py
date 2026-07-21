from __future__ import annotations

import html
import re

from loguru import logger

from app.agent.state import AgentState
from app.classifier.predict import ClassifierNotTrainedError, predict_category
from app.core.additional_checks import format_additional_checks_block
from app.core.business_type import (
    contains_forbidden_words,
    is_known_business_type,
    is_unknown_business_type,
    looks_like_business_query,
    looks_like_prompt_injection,
    resolve_business_type,
)
from app.core.config import get_settings
from app.core.npa_titles import federal_sp42_label
from app.core.regions import FEDERAL_CODE, get_region
from app.llm.base import DEFAULT_MAX_TOKENS, LLMProviderError
from app.llm.factory import get_llm_provider
from app.llm.parsing import LLMParsingError, parse_json_response
from app.llm.prompts import (
    BUSINESS_TYPE_NORMALIZATION_SYSTEM_PROMPT,
    COMPARISON_SYSTEM_PROMPT,
    EXTRACTION_SYSTEM_PROMPT,
    build_business_type_normalization_prompt,
    build_comparison_prompt,
    build_extraction_prompt,
)
from app.llm.schemas import CommonRequirementItem, ComparisonResult, ExtractionResult, RequirementItem
from app.vectorstore.types import RetrievedChunk
from app.vectorstore.retriever import retrieve

TOP_K_PER_CATEGORY = 5

DISCLAIMER_TEXT = (
    "\n\n⚠️ Ответ носит справочный характер и не является юридической консультацией. "
    "Сверьте указанные пункты в тексте нормативного акта (название источника выше), "
    "прежде чем опираться на него."
)

MAX_WORDS_FOR_RAW_BUSINESS_TYPE = 3

INVALID_BUSINESS_TYPE_ERROR = (
    "Не удалось распознать тип бизнеса. Укажите объект коротко "
    "(например: кафе, автомойка, склад, медицинский центр)."
)

FORBIDDEN_CONTENT_ERROR = (
    "Запрос выглядит как просьба про секреты или доступы. "
    "Я помогаю только со строительными нормативами для типа бизнеса."
)

_MISSING_IN_FRAGMENTS_RE = re.compile(
    r"(не\s+найдено\s+в\s+предоставленных\s+фрагментах|"
    r"в\s+нормативе\s+региона\s+не\s+указано)\.?",
    re.IGNORECASE,
)
_MISSING_REGION_VALUE = "региональные требования отсутствуют"
_MISSING_REGION_VALUE_ALT = "в нормативе региона не указано"

_CITATION_PREFIXES = (
    "пп.",
    "п.",
    "пункты",
    "пункта",
    "пункту",
    "пунктом",
    "пункте",
    "пункт",
)


def _validate_business_type(business_type: str) -> str | None:
    """Возвращает текст ошибки или None, если тип бизнеса допустим."""
    if contains_forbidden_words(business_type) or looks_like_prompt_injection(business_type):
        return FORBIDDEN_CONTENT_ERROR
    if is_unknown_business_type(business_type):
        return INVALID_BUSINESS_TYPE_ERROR
    if not looks_like_business_query(business_type):
        return INVALID_BUSINESS_TYPE_ERROR
    if not is_known_business_type(business_type):
        return INVALID_BUSINESS_TYPE_ERROR
    return None


def normalize_business_type(state: AgentState) -> AgentState:
    """Короткие названия оставляем; длинные фразы сжимаем через LLM перед retrieval."""
    raw_text = (state.get("business_type") or "").strip()
    if not raw_text:
        return state

    if contains_forbidden_words(raw_text) or looks_like_prompt_injection(raw_text):
        return {**state, "error": FORBIDDEN_CONTENT_ERROR}

    if not looks_like_business_query(raw_text):
        return {**state, "error": INVALID_BUSINESS_TYPE_ERROR}

    if len(raw_text.split()) <= MAX_WORDS_FOR_RAW_BUSINESS_TYPE:
        resolved = resolve_business_type(raw_text)
        validation_error = _validate_business_type(resolved)
        if validation_error:
            return {**state, "error": validation_error}
        if resolved != raw_text.strip().lower().strip("«»\"'."):
            logger.info(f"тип бизнеса исправлен (fuzzy): «{raw_text}» → «{resolved}»")
            return {**state, "business_type": resolved, "business_type_raw": raw_text}
        return {**state, "business_type": resolved}

    try:
        provider = get_llm_provider()
        normalized = provider.complete(
            BUSINESS_TYPE_NORMALIZATION_SYSTEM_PROMPT,
            build_business_type_normalization_prompt(raw_text),
            max_tokens=64,
        )
    except LLMProviderError as exc:
        logger.warning(f"не удалось нормализовать тип бизнеса, использую исходный текст: {exc}")
        return state

    normalized = resolve_business_type(normalized.strip().strip("«»\"'.").strip())
    if not normalized or is_unknown_business_type(normalized):
        return {**state, "error": INVALID_BUSINESS_TYPE_ERROR}

    validation_error = _validate_business_type(normalized)
    if validation_error:
        return {**state, "error": validation_error}

    logger.info(f"тип бизнеса нормализован: «{raw_text}» → «{normalized}»")
    return {**state, "business_type": normalized, "business_type_raw": raw_text}


def understand_query(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    business_type = (state.get("business_type") or "").strip()
    if not business_type:
        return {**state, "error": "Не указан тип бизнес-объекта."}

    validation_error = _validate_business_type(business_type)
    if validation_error:
        return {**state, "error": validation_error}

    if not state.get("region_a"):
        return {**state, "error": "Не указан регион."}
    if state.get("mode") == "compare" and not state.get("region_b"):
        return {**state, "error": "Для режима сравнения нужно указать два региона."}
    return {**state, "business_type": business_type}


def _retrieve_for_region(business_type: str, region_code: str) -> list[RetrievedChunk]:
    # по категориям отдельно — иначе top_k забивают чанки про «документы»
    found_ids: set[str] = set()
    result: list[RetrievedChunk] = []

    for category in get_settings().requirement_categories:
        query = f"{business_type}: {category}"
        for chunk in retrieve(query, region_code=region_code, top_k=TOP_K_PER_CATEGORY):
            if chunk.id not in found_ids:
                found_ids.add(chunk.id)
                result.append(chunk)

    return result


def retrieve_chunks(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    business_type = state["business_type"]
    chunks_a = _retrieve_for_region(business_type, state["region_a"])
    logger.info(f"регион A ({state['region_a']}): найдено {len(chunks_a)} чанков")

    chunks_federal = _retrieve_for_region(business_type, FEDERAL_CODE)
    logger.info(f"федеральный уровень: найдено {len(chunks_federal)} чанков")

    new_state: AgentState = {**state, "retrieved_a": chunks_a, "retrieved_federal": chunks_federal}

    if state.get("mode") == "compare" and state.get("region_b"):
        chunks_b = _retrieve_for_region(business_type, state["region_b"])
        logger.info(f"регион B ({state['region_b']}): найдено {len(chunks_b)} чанков")
        new_state["retrieved_b"] = chunks_b

    if not chunks_a and not chunks_federal:
        new_state["error"] = (
            "Не нашлось релевантных фрагментов норматива. Проверьте, что ingestion "
            "и построение векторного индекса были выполнены."
        )

    return new_state


def _classify_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    from app.llm.schemas import _coerce_category

    for chunk in chunks:
        if chunk.category:
            chunk.category = str(_coerce_category(chunk.category))
            continue
        try:
            predicted = predict_category(chunk.text)
            chunk.category = str(_coerce_category(predicted))
        except ClassifierNotTrainedError as exc:
            logger.warning(f"классификатор не обучен: {exc}")
            break
    return chunks


def classify_requirements(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    new_state: AgentState = {**state, "retrieved_a": _classify_chunks(state.get("retrieved_a", []))}
    if state.get("retrieved_b") is not None:
        new_state["retrieved_b"] = _classify_chunks(state["retrieved_b"])
    if state.get("retrieved_federal") is not None:
        new_state["retrieved_federal"] = _classify_chunks(state["retrieved_federal"])
    return new_state


def llm_compare_or_extract(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    try:
        provider = get_llm_provider()
    except LLMProviderError as exc:
        return {**state, "error": str(exc)}

    if state["mode"] == "info":
        prompt = build_extraction_prompt(
            state["business_type"],
            state["region_a"],
            state.get("retrieved_a", []),
            state.get("retrieved_federal", []),
        )
        try:
            raw_answer = provider.complete(
                EXTRACTION_SYSTEM_PROMPT,
                prompt,
                max_tokens=DEFAULT_MAX_TOKENS,
            )
            logger.debug(f"сырой ответ LLM (extraction): {raw_answer}")
            extraction = parse_json_response(raw_answer, ExtractionResult)
        except (LLMProviderError, LLMParsingError) as exc:
            logger.error(f"не удалось получить extraction от LLM: {exc}")
            return {**state, "error": str(exc)}
        # коды/тип берём из запроса, не из ответа модели
        allowed_chunks = list(state.get("retrieved_a", [])) + list(state.get("retrieved_federal", []))
        grounded_items = _filter_grounded_items(extraction.items, allowed_chunks)
        extraction = extraction.model_copy(
            update={
                "region_code": state["region_a"],
                "business_type": state["business_type"],
                "items": grounded_items,
            }
        )
        return {**state, "extraction": extraction}

    prompt = build_comparison_prompt(
        state["business_type"],
        state["region_a"],
        state.get("retrieved_a", []),
        state["region_b"],
        state.get("retrieved_b", []),
        state.get("retrieved_federal", []),
    )
    try:
        raw_answer = provider.complete(
            COMPARISON_SYSTEM_PROMPT,
            prompt,
            max_tokens=DEFAULT_MAX_TOKENS,
        )
        logger.debug(f"сырой ответ LLM (compare): {raw_answer}")
        comparison = parse_json_response(raw_answer, ComparisonResult)
    except (LLMProviderError, LLMParsingError) as exc:
        logger.error(f"не удалось получить comparison от LLM: {exc}")
        return {**state, "error": str(exc)}

    region_a = get_region(state["region_a"])
    region_b = get_region(state["region_b"])
    allowed_chunks = (
        list(state.get("retrieved_a", []))
        + list(state.get("retrieved_b", []))
        + list(state.get("retrieved_federal", []))
    )
    grounded_commons = _filter_grounded_commons(comparison.common_requirements, allowed_chunks)
    cleaned_differences = [
        diff.model_copy(
            update={
                "summary": _replace_region_placeholders(diff.summary, region_a.display_name, region_b.display_name),
                "region_a_value": _replace_region_placeholders(
                    diff.region_a_value, region_a.display_name, region_b.display_name
                ),
                "region_b_value": _replace_region_placeholders(
                    diff.region_b_value, region_a.display_name, region_b.display_name
                ),
            }
        )
        for diff in comparison.differences
    ]
    # коды/тип из запроса — модель иногда подставляет display_name и ломает рендер
    comparison = comparison.model_copy(
        update={
            "region_a": state["region_a"],
            "region_b": state["region_b"],
            "business_type": state["business_type"],
            "overall_summary": _replace_region_placeholders(
                comparison.overall_summary, region_a.display_name, region_b.display_name
            ),
            "common_requirements": grounded_commons,
            "differences": cleaned_differences,
        }
    )
    return {**state, "comparison": comparison}


CATEGORY_LABELS: dict[str, str] = {
    "земельно_правовые": "Земельно-правовые требования",
    "градостроительные": "Градостроительные нормы",
    "пожарная_безопасность": "Пожарная безопасность",
    "санитарные_экологические": "Санитарные и экологические нормы",
    "архитектурный_облик": "Архитектурный облик",
    "дорожное_согласование": "Дорожное согласование",
    "налоги_поддержка": "Налоги и меры поддержки",
    "процедуры_согласования": "Процедуры согласования",
    "подключение_к_сетям": "Подключение к сетям",
    "сроки_и_документы": "Сроки и документы",
    # legacy labels (на случай старых тестов/данных до coerce)
    "сроки": "Сроки и документы",
    "документы": "Сроки и документы",
    "состав_проекта": "Градостроительные нормы",
    "иные_требования": "Градостроительные нормы",
}


def _esc(text: str) -> str:
    return html.escape(text, quote=False)


def _category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").capitalize())


def _group_by_category(items: list) -> dict[str, list]:
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(item.category, []).append(item)
    return groups


def _greeting_for_info(business_type: str, region_locative: str) -> str:
    return (
        f"Я вас понял! Вы хотите открыть «{_esc(business_type)}» в {region_locative} — "
        f"ниже требования по нормативам."
    )


def _greeting_for_comparison(business_type: str, region_a_locative: str, region_b_locative: str) -> str:
    return (
        f"Я вас понял! Сравниваю требования для «{_esc(business_type)}» "
        f"в {region_a_locative} и в {region_b_locative}."
    )


def _normalize_citation(citation: str) -> str:
    cleaned = (citation or "").strip()
    while cleaned:
        lowered = cleaned.lower()
        matched = False
        for prefix in _CITATION_PREFIXES:
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix):].lstrip(" .;")
                matched = True
                break
        if not matched:
            break
    return cleaned or (citation or "").strip()


def _citation_matches_chunks(citation: str, chunks: list[RetrievedChunk]) -> bool:
    """Проверяет, что номер пункта есть среди retrieved-чанков — отсекает галлюцинации."""
    normalized = _normalize_citation(citation)
    if not normalized or normalized.lower() in {"без номера", "n/a", "-", "—"}:
        return False
    for chunk in chunks:
        section = (chunk.section_number or "").strip()
        if not section:
            continue
        if (
            section == normalized
            or section.startswith(normalized + ".")
            or normalized.startswith(section + ".")
        ):
            return True
    return False


def _filter_grounded_items(
    items: list[RequirementItem],
    chunks: list[RetrievedChunk],
) -> list[RequirementItem]:
    grounded: list[RequirementItem] = []
    for item in items:
        if _citation_matches_chunks(item.citation, chunks):
            grounded.append(item)
        else:
            logger.warning(
                f"отброшен item без опоры на чанки: citation={item.citation!r} "
                f"desc={item.description[:80]!r}"
            )
    return grounded


def _filter_grounded_commons(
    items: list[CommonRequirementItem],
    chunks: list[RetrievedChunk],
) -> list[CommonRequirementItem]:
    grounded: list[CommonRequirementItem] = []
    for item in items:
        # совпадение без цитаты оставляем, если описание непустое — федеральный фон
        if item.citation and not _citation_matches_chunks(item.citation, chunks):
            logger.warning(
                f"отброшен common без опоры на чанки: citation={item.citation!r} "
                f"desc={item.description[:80]!r}"
            )
            continue
        grounded.append(item)
    return grounded


_REGION_PLACEHOLDER_RE = re.compile(
    r"\b[Рр]егион(?:е|а|у|ом|е)?\s*[AАBВab]\b",
    re.UNICODE,
)


def _replace_region_placeholders(text: str, region_a_name: str, region_b_name: str) -> str:
    """«регион A/B» → реальные названия регионов."""

    def _sub(match: re.Match[str]) -> str:
        token = match.group(0)
        marker = token[-1].upper()
        if marker in {"A", "А"}:
            return region_a_name
        if marker in {"B", "В"}:
            return region_b_name
        return token

    return _REGION_PLACEHOLDER_RE.sub(_sub, text or "")


def _citation_suffix(citation: str, source_level: str) -> str:
    normalized = _normalize_citation(citation)
    if not normalized:
        return ""
    if source_level == "федеральный":
        return f"({_esc(federal_sp42_label())}, п. {_esc(normalized)})"
    return f"(п. {_esc(normalized)})"


def _humanize_missing_value(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return _MISSING_REGION_VALUE
    lowered = cleaned.lower()
    if "не указано" in lowered or "отсутств" in lowered or "фрагментах" in lowered:
        # чередование формулировок для разнообразия
        return _MISSING_REGION_VALUE if hash(cleaned) % 2 == 0 else _MISSING_REGION_VALUE_ALT
    replaced = _MISSING_IN_FRAGMENTS_RE.sub(_MISSING_REGION_VALUE, cleaned).strip()
    return replaced or _MISSING_REGION_VALUE


def _is_concrete_common(item: CommonRequirementItem) -> bool:
    text = (item.description or "").strip()
    if len(text) < 20:
        return False
    lowered = text.lower()
    vague_tokens = ("совпада", "одинаков", "общие правила", "в целом")
    if len(text) < 40 and any(token in lowered for token in vague_tokens):
        return False
    return True


def _render_extraction(extraction: ExtractionResult) -> str:
    region = get_region(extraction.region_code)
    sp_label = federal_sp42_label()
    lines = [
        f"<b>{_greeting_for_info(extraction.business_type, region.name_locative)}</b>",
        f"📖 Правовое регулирование: {region.document_title} (проверено {region.last_verified})",
        f"📖 Федеральные нормы (применяются при отсутствии региональных): {sp_label}.",
    ]

    groups = _group_by_category(extraction.items)
    categories = list(get_settings().requirement_categories)
    empty_categories = [c for c in categories if not groups.get(c)]
    filled_categories = [c for c in categories if groups.get(c)]

    if empty_categories and filled_categories:
        empty_labels = ", ".join(_category_label(c) for c in empty_categories)
        lines.append(
            f"\nПо остальным категориям данные не найдены "
            f"({_esc(empty_labels)})."
        )

    shown_any = False
    for category in filled_categories:
        items = groups.get(category) or []
        shown_any = True
        lines.append(f"\n<b>{_category_label(category)}</b>")

        specific_items = [item for item in items if item.is_specific]
        general_items = [item for item in items if not item.is_specific]
        only_federal = all(item.source_level == "федеральный" for item in items)

        if only_federal:
            lines.append(
                f"Специальных региональных норм нет — ниже применимые федеральные ({sp_label}):"
            )
        elif not specific_items and general_items:
            lines.append(
                f"Специальных требований к «{_esc(extraction.business_type)}» здесь нет, "
                f"но применяются общие нормы:"
            )

        ordered = specific_items + general_items if specific_items else general_items
        if specific_items and general_items:
            for item in specific_items:
                suffix = _citation_suffix(item.citation, item.source_level)
                lines.append(f"• {_esc(item.description)}" + (f" {suffix}" if suffix else ""))
            lines.append("Плюс действуют общие нормы:")
            for item in general_items:
                suffix = _citation_suffix(item.citation, item.source_level)
                lines.append(f"• {_esc(item.description)}" + (f" {suffix}" if suffix else ""))
        else:
            for item in ordered:
                suffix = _citation_suffix(item.citation, item.source_level)
                lines.append(f"• {_esc(item.description)}" + (f" {suffix}" if suffix else ""))

    if not shown_any:
        lines.append(
            "\nВ региональном нормативе требования по данному объекту не установлены. "
            f"Рекомендуем проверить федеральные нормы ({sp_label}) и актуальные ПЗЗ территории."
        )

    lines.append(format_additional_checks_block(extraction.business_type))
    return "\n".join(lines)


def _render_comparison(comparison: ComparisonResult) -> str:
    region_a = get_region(comparison.region_a)
    region_b = get_region(comparison.region_b)
    sp_label = federal_sp42_label()
    lines = [
        f"<b>{_greeting_for_comparison(comparison.business_type, region_a.name_locative, region_b.name_locative)}</b>",
        f"📖 {region_a.display_name} — правовое регулирование: {region_a.document_title} "
        f"(проверено {region_a.last_verified})",
        f"📖 {region_b.display_name} — правовое регулирование: {region_b.document_title} "
        f"(проверено {region_b.last_verified})",
        f"📖 Федеральные нормы (применяются при отсутствии региональных): {sp_label}.",
        f"\n{_esc(comparison.overall_summary)}",
    ]

    commons = [item for item in (comparison.common_requirements or []) if _is_concrete_common(item)]
    differences = list(comparison.differences or [])

    # сначала различия, потом совпадения (только конкретные)
    if differences:
        lines.append("\n<b>Чем отличаются</b>")
        groups = _group_by_category(differences)
        diff_number = 1
        for category in get_settings().requirement_categories:
            category_diffs = groups.get(category) or []
            if not category_diffs:
                continue
            lines.append(f"\n<b>{_category_label(category)}</b>")
            specific = [diff for diff in category_diffs if diff.is_specific]
            general = [diff for diff in category_diffs if not diff.is_specific]
            if not specific and general:
                lines.append(
                    f"Специальных норм для «{_esc(comparison.business_type)}» здесь нет — "
                    f"сравниваю общие требования:"
                )
            for diff in specific + general:
                federal_note = f" (по {sp_label})" if diff.source_level == "федеральный" else ""
                lines.append(f"{diff_number}. {_esc(diff.summary)}{federal_note}")
                lines.append(
                    f"  🔵 <b>{region_a.display_name}:</b> "
                    f"{_esc(_humanize_missing_value(diff.region_a_value))}"
                )
                lines.append(
                    f"  🟢 <b>{region_b.display_name}:</b> "
                    f"{_esc(_humanize_missing_value(diff.region_b_value))}"
                )
                diff_number += 1
    else:
        lines.append("\n<b>Чем отличаются</b>\nРазличий не обнаружено.")

    if commons:
        lines.append("\n<b>Что совпадает</b>")
        lines.append(
            "Эти требования одинаковы или одинаково опираются на федеральные нормы — "
            "при расширении бизнеса на них можно ориентироваться как на общие:"
        )
        for index, item in enumerate(commons, start=1):
            suffix = _citation_suffix(item.citation, item.source_level)
            federal_note = f" (по {sp_label})" if item.source_level == "федеральный" else ""
            line = f"{index}. {_esc(item.description)}{federal_note}"
            if suffix:
                line = f"{line} {suffix}"
            lines.append(line)
    elif not differences:
        lines.append(
            "\nТребования не установлены ни на региональном, ни на федеральном уровне "
            "в объёме доступных источников. Рекомендуем проверить ПЗЗ и отраслевые НПА напрямую."
        )

    lines.append(format_additional_checks_block(comparison.business_type))
    return "\n".join(lines)


def format_response(state: AgentState) -> AgentState:
    if state.get("error"):
        return {**state, "response_text": f"Не удалось получить ответ: {_esc(state['error'])}"}

    prefix = ""
    if state.get("business_type_raw"):
        prefix = f"<i>Распознанный тип бизнеса: «{_esc(state['business_type'])}»</i>\n\n"

    if state["mode"] == "info" and state.get("extraction"):
        body = _render_extraction(state["extraction"])
        return {**state, "response_text": prefix + body + DISCLAIMER_TEXT}

    if state["mode"] == "compare" and state.get("comparison"):
        body = _render_comparison(state["comparison"])
        return {**state, "response_text": prefix + body + DISCLAIMER_TEXT}

    return {**state, "response_text": "Не удалось сформировать ответ по имеющимся данным."}
