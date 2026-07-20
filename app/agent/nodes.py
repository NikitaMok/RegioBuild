from __future__ import annotations

import html
import re

from loguru import logger

from app.agent.state import AgentState
from app.classifier.predict import ClassifierNotTrainedError, predict_category
from app.core.business_type import (
    contains_forbidden_words,
    is_known_business_type,
    is_unknown_business_type,
    looks_like_business_query,
)
from app.core.config import get_settings
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
from app.llm.schemas import ComparisonResult, ExtractionResult
from app.vectorstore.retriever import RetrievedChunk, retrieve

TOP_K_PER_CATEGORY = 5

DISCLAIMER_TEXT = (
    "\n\n⚠️ Ответ может быть неполным. Сверьте указанные пункты в тексте "
    "нормативного акта (название источника выше), прежде чем опираться на него."
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
    r"не\s+найдено\s+в\s+предоставленных\s+фрагментах\.?",
    re.IGNORECASE,
)
_MISSING_REGION_VALUE = "в нормативе региона не указано"

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
    if contains_forbidden_words(business_type):
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

    if contains_forbidden_words(raw_text):
        return {**state, "error": FORBIDDEN_CONTENT_ERROR}

    if not looks_like_business_query(raw_text):
        return {**state, "error": INVALID_BUSINESS_TYPE_ERROR}

    if len(raw_text.split()) <= MAX_WORDS_FOR_RAW_BUSINESS_TYPE:
        validation_error = _validate_business_type(raw_text)
        if validation_error:
            return {**state, "error": validation_error}
        return state

    try:
        provider = get_llm_provider()
        normalized = provider.complete(
            BUSINESS_TYPE_NORMALIZATION_SYSTEM_PROMPT,
            build_business_type_normalization_prompt(raw_text),
            max_tokens=DEFAULT_MAX_TOKENS,
        )
    except LLMProviderError as exc:
        logger.warning(f"не удалось нормализовать тип бизнеса, использую исходный текст: {exc}")
        return state

    normalized = normalized.strip().strip("«»\"'.").strip()
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
    for chunk in chunks:
        if chunk.category:
            continue
        try:
            chunk.category = predict_category(chunk.text)
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
        extraction = extraction.model_copy(
            update={
                "region_code": state["region_a"],
                "business_type": state["business_type"],
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
    # коды/тип из запроса — модель иногда подставляет display_name и ломает рендер
    comparison = comparison.model_copy(
        update={
            "region_a": state["region_a"],
            "region_b": state["region_b"],
            "business_type": state["business_type"],
        }
    )
    return {**state, "comparison": comparison}


CATEGORY_LABELS: dict[str, str] = {
    "сроки": "⏱ Сроки",
    "документы": "📄 Необходимые документы",
    "подключение_к_сетям": "🔌 Подключение к сетям",
    "состав_проекта": "📐 Технические параметры",
    "иные_требования": "🏞 Благоустройство и размещение",
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


def _greeting_for_comparison(business_type: str, region_a_name: str, region_b_name: str) -> str:
    return (
        f"Я вас понял! Сравниваю требования для «{_esc(business_type)}»: "
        f"{region_a_name} и {region_b_name}."
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


def _citation_suffix(citation: str, source_level: str) -> str:
    normalized = _normalize_citation(citation)
    if source_level == "федеральный":
        return f"(СП 42.13330.2016, п. {_esc(normalized)})"
    return f"(п. {_esc(normalized)})"


def _humanize_missing_value(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return _MISSING_REGION_VALUE
    replaced = _MISSING_IN_FRAGMENTS_RE.sub(_MISSING_REGION_VALUE, cleaned).strip()
    return replaced or _MISSING_REGION_VALUE


def _render_extraction(extraction: ExtractionResult) -> str:
    region = get_region(extraction.region_code)
    lines = [
        f"<b>{_greeting_for_info(extraction.business_type, region.name_locative)}</b>",
        f"📖 Регулируется: {region.document_title} (проверено {region.last_verified})",
        "📖 Плюс федеральный уровень: СП 42.13330.2016 — применяется там, где регион не устанавливает своих правил.",
    ]

    groups = _group_by_category(extraction.items)
    for category in get_settings().requirement_categories:
        items = groups.get(category) or []
        lines.append(f"\n<b>{_category_label(category)}</b>")

        if not items:
            lines.append("В региональном акте по этой категории ничего не найдено.")
            continue

        specific_items = [item for item in items if item.is_specific]
        general_items = [item for item in items if not item.is_specific]
        only_federal = all(item.source_level == "федеральный" for item in items)

        if only_federal:
            lines.append(
                "Специальных региональных норм нет — ниже применимые федеральные (СП 42.13330.2016):"
            )
        elif not specific_items and general_items:
            lines.append(
                f"Специальных требований к «{_esc(extraction.business_type)}» здесь нет, "
                f"но применяются общие нормы:"
            )

        if specific_items:
            for item in specific_items:
                lines.append(
                    f"• {_esc(item.description)} {_citation_suffix(item.citation, item.source_level)}"
                )
            if general_items:
                lines.append("Плюс действуют общие нормы:")
                for item in general_items:
                    lines.append(
                        f"• {_esc(item.description)} {_citation_suffix(item.citation, item.source_level)}"
                    )
        else:
            for item in general_items:
                lines.append(
                    f"• {_esc(item.description)} {_citation_suffix(item.citation, item.source_level)}"
                )

    return "\n".join(lines)


def _render_comparison(comparison: ComparisonResult) -> str:
    region_a = get_region(comparison.region_a)
    region_b = get_region(comparison.region_b)
    lines = [
        f"<b>{_greeting_for_comparison(comparison.business_type, region_a.display_name, region_b.display_name)}</b>",
        f"📖 {region_a.display_name} — регулируется: {region_a.document_title} "
        f"(проверено {region_a.last_verified})",
        f"📖 {region_b.display_name} — регулируется: {region_b.document_title} "
        f"(проверено {region_b.last_verified})",
        "📖 Плюс федеральный уровень: СП 42.13330.2016 — общий для обоих регионов.",
        f"\n{_esc(comparison.overall_summary)}",
    ]

    groups = _group_by_category(comparison.differences)
    for category in get_settings().requirement_categories:
        differences = groups.get(category) or []
        lines.append(f"\n<b>{_category_label(category)}</b>")

        if not differences:
            lines.append("По этой категории различий в найденных нормах нет.")
            continue

        specific = [diff for diff in differences if diff.is_specific]
        general = [diff for diff in differences if not diff.is_specific]
        only_federal = all(diff.source_level == "федеральный" for diff in differences)

        if only_federal:
            lines.append("Сравниваю применимые федеральные нормы (региональных отличий нет):")
        elif not specific and general:
            lines.append(
                f"Специальных норм для «{_esc(comparison.business_type)}» здесь нет — "
                f"сравниваю общие требования, которые применяются к нему:"
            )

        for diff in specific + general:
            federal_note = " (по СП 42.13330.2016)" if diff.source_level == "федеральный" else ""
            lines.append(f"• {_esc(diff.summary)}{federal_note}")
            lines.append(
                f"  🔵 <b>{region_a.display_name}:</b> {_esc(_humanize_missing_value(diff.region_a_value))}"
            )
            lines.append(
                f"  🟢 <b>{region_b.display_name}:</b> {_esc(_humanize_missing_value(diff.region_b_value))}"
            )

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
