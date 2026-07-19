from __future__ import annotations

import html

from loguru import logger

from app.agent.state import AgentState
from app.classifier.predict import ClassifierNotTrainedError, predict_category
from app.core.config import get_settings
from app.core.regions import FEDERAL_CODE, get_region
from app.llm.base import LLMProviderError
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
    "\n\n⚠️ Я стараюсь помочь и сэкономить вам время, но я всё ещё учусь — "
    "ответ может быть неполным или неточным. Обязательно сверьте указанные "
    "пункты в тексте нормативного акта (название источника указано выше) "
    "перед принятием решения."
)

# Если пользователь укладывается в пару слов ("автомойка", "цветочный магазин"),
# это почти наверняка уже готовый тип бизнеса — незачем тратить на него вызов LLM.
MAX_WORDS_FOR_RAW_BUSINESS_TYPE = 3


def normalize_business_type(state: AgentState) -> AgentState:
    """Люди часто пишут не «автомойка», а целое предложение вроде «хочу построить
    автомойку в Краснодаре, у меня уже есть такая в московской области». Эмбеддинг
    такой фразы плохо похож на текст норматива, и retrieval ничего не находит.
    Здесь просим LLM вытащить из фразы короткий тип бизнеса перед поиском."""
    raw_text = (state.get("business_type") or "").strip()
    if not raw_text or len(raw_text.split()) <= MAX_WORDS_FOR_RAW_BUSINESS_TYPE:
        return state

    try:
        provider = get_llm_provider()
        normalized = provider.complete(
            BUSINESS_TYPE_NORMALIZATION_SYSTEM_PROMPT,
            build_business_type_normalization_prompt(raw_text),
        )
    except LLMProviderError as exc:
        logger.warning(f"не удалось нормализовать тип бизнеса, использую исходный текст: {exc}")
        return state

    normalized = normalized.strip().strip("«»\"'.").strip()
    if not normalized:
        return state

    logger.info(f"тип бизнеса нормализован: «{raw_text}» → «{normalized}»")
    return {**state, "business_type": normalized, "business_type_raw": raw_text}


def understand_query(state: AgentState) -> AgentState:
    business_type = (state.get("business_type") or "").strip()
    if not business_type:
        return {**state, "error": "Не указан тип бизнес-объекта."}
    if not state.get("region_a"):
        return {**state, "error": "Не указан регион."}
    if state.get("mode") == "compare" and not state.get("region_b"):
        return {**state, "error": "Для режима сравнения нужно указать два региона."}
    return {**state, "business_type": business_type}


def _retrieve_for_region(business_type: str, region_code: str) -> list[RetrievedChunk]:
    # один общий запрос "бизнес: требования" почти всегда вытягивает top_k чанков
    # только про документы — они самые частотные в тексте норматива. Поэтому гоняем
    # retrieval отдельно по каждой категории и потом склеиваем без дублей по id.
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

    # федеральный СП подтягиваем всегда одним и тем же способом, независимо
    # от режима — это фон, общий для любого региона (см. build_extraction_prompt)
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


# TODO: одинаковые запросы (тот же бизнес + регион) сейчас каждый раз идут в LLM
# заново — если бот наберёт трафик, стоит закешировать по (business_type, region)
# хотя бы на день, ответ всё равно не меняется чаще, чем сами нормативы.
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
            raw_answer = provider.complete(EXTRACTION_SYSTEM_PROMPT, prompt)
            logger.debug(f"сырой ответ LLM (extraction): {raw_answer}")
            extraction = parse_json_response(raw_answer, ExtractionResult)
        except (LLMProviderError, LLMParsingError) as exc:
            logger.error(f"не удалось получить extraction от LLM: {exc}")
            return {**state, "error": str(exc)}
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
        raw_answer = provider.complete(COMPARISON_SYSTEM_PROMPT, prompt)
        logger.debug(f"сырой ответ LLM (compare): {raw_answer}")
        comparison = parse_json_response(raw_answer, ComparisonResult)
    except (LLMProviderError, LLMParsingError) as exc:
        logger.error(f"не удалось получить comparison от LLM: {exc}")
        return {**state, "error": str(exc)}
    # модель иногда пишет в region_a/region_b человеческое имя вместо кода
    # ("Новосибирская область") — тогда get_region в рендере падает с 500.
    # Коды регионов нам уже известны из запроса пользователя, ими и пользуемся.
    comparison = comparison.model_copy(
        update={
            "region_a": state["region_a"],
            "region_b": state["region_b"],
            "business_type": state["business_type"],
        }
    )
    return {**state, "comparison": comparison}


# Человеческие подписи вместо сырых имён категорий из классификатора —
# "состав_проекта" сам по себе ничего не говорит обычному пользователю, поэтому
# подпись расшифровываем: речь именно о том, что должно быть в проектной
# документации, а не о требованиях к самому бизнесу.
CATEGORY_LABELS: dict[str, str] = {
    "сроки": "⏱ Сроки",
    "документы": "📄 Необходимые документы",
    "подключение_к_сетям": "🔌 Подключение к сетям",
    "состав_проекта": "📋 Состав проектной документации",
    "иные_требования": "📌 Иные требования",
}


def _esc(text: str) -> str:
    """Ответы собираем как HTML для Telegram (жирные заголовки и т.п.), а текст
    внутри частично приходит от LLM — если там окажется "<" или "&" (например,
    "высота < 50 м"), Telegram откажется отправлять всё сообщение целиком."""
    return html.escape(text, quote=False)


def _category_label(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").capitalize())


def _group_by_category(items: list) -> dict[str, list]:
    groups: dict[str, list] = {}
    for item in items:
        groups.setdefault(item.category, []).append(item)
    return groups


# Пишем сами, а не просим LLM — так текст предсказуемый и не повторяет
# слово в слово загрузочное сообщение бота ("Ищу требования для...").
def _greeting_for_info(business_type: str, region_name: str) -> str:
    return (
        f"Я вас понял! Вы хотите открыть «{_esc(business_type)}» в {region_name} — "
        f"с радостью помогу разобраться с требованиями."
    )


def _greeting_for_comparison(business_type: str, region_a_name: str, region_b_name: str) -> str:
    return (
        f"Я вас понял! Вы хотите сравнить требования для «{_esc(business_type)}»: "
        f"{region_a_name} и {region_b_name} — с радостью помогу разобраться."
    )


def _citation_suffix(citation: str, source_level: str) -> str:
    # федеральную норму нельзя подписывать просто "(п. X)" — пункт X в СП
    # 42.13330 и в региональном акте это совершенно разные документы, и без
    # явной пометки пользователь не поймёт, где именно искать первоисточник
    if source_level == "федеральный":
        return f"(СП 42.13330.2016, п. {_esc(citation)})"
    return f"(п. {_esc(citation)})"


def _render_extraction(extraction: ExtractionResult) -> str:
    region = get_region(extraction.region_code)
    lines = [
        f"<b>{_greeting_for_info(extraction.business_type, region.display_name)}</b>",
        f"📖 Регулируется: {region.document_title} (проверено {region.last_verified})",
        "📖 Плюс федеральный уровень: СП 42.13330.2016 — применяется там, где регион не устанавливает своих правил.",
    ]

    groups = _group_by_category(extraction.items)
    found_any = False
    for category in get_settings().requirement_categories:
        items = groups.get(category)
        if not items:
            continue
        found_any = True
        specific_items = [item for item in items if item.is_specific]
        general_items = [item for item in items if not item.is_specific]

        lines.append(f"\n<b>{_category_label(category)}</b>")
        if specific_items:
            for item in specific_items:
                lines.append(f"• {_esc(item.description)} {_citation_suffix(item.citation, item.source_level)}")
            if general_items:
                lines.append("Плюс действуют общие нормы:")
                for item in general_items:
                    lines.append(f"• {_esc(item.description)} {_citation_suffix(item.citation, item.source_level)}")
        else:
            # специальных норм под этот бизнес нет — но нашлось что-то общее,
            # применимое к нему. Раньше в этом случае категория просто пропадала
            # из ответа, и выглядело так, будто бот вообще не искал по ней
            lines.append(
                f"Специальных требований к «{_esc(extraction.business_type)}» здесь нет, "
                f"но применяются общие нормы:"
            )
            for item in general_items:
                lines.append(f"• {_esc(item.description)} {_citation_suffix(item.citation, item.source_level)}")

    if not found_any:
        lines.append("\nПо данному запросу не найдено структурированных требований в источнике.")

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
    found_any = False
    for category in get_settings().requirement_categories:
        differences = groups.get(category)
        if not differences:
            continue
        found_any = True
        specific = [diff for diff in differences if diff.is_specific]
        general = [diff for diff in differences if not diff.is_specific]

        lines.append(f"\n<b>{_category_label(category)}</b>")
        if not specific and general:
            lines.append(
                f"Специальных норм для «{_esc(comparison.business_type)}» здесь нет — "
                f"сравниваю общие требования, которые применяются к нему:"
            )
        for diff in specific + general:
            federal_note = " (по СП 42.13330.2016)" if diff.source_level == "федеральный" else ""
            lines.append(f"• {_esc(diff.summary)}{federal_note}")
            lines.append(f"  ▫️ <b>{region_a.display_name}:</b> {_esc(diff.region_a_value)}")
            lines.append(f"  ▫️ <b>{region_b.display_name}:</b> {_esc(diff.region_b_value)}")

    if not found_any:
        lines.append("\nКонкретных различий по найденным пунктам не выявлено.")

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
