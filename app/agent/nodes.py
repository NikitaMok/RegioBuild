from __future__ import annotations

import html
import re

from loguru import logger

from app.agent.state import AgentState
from app.classifier.predict import ClassifierNotTrainedError, predict_category
from app.core.additional_checks import format_additional_checks_block
from app.core.business_type import (
    contains_forbidden_words,
    extract_known_business_type,
    is_known_business_type,
    is_unknown_business_type,
    looks_like_business_query,
    looks_like_prompt_injection,
    resolve_business_type,
)
from app.core.config import get_settings
from app.core.legal import DISCLAIMER_TEXT
from app.core.npa_titles import (
    expand_npa_label,
    federal_source_url,
    federal_sp42_label,
    full_federal_cite_from_citation,
)
from app.core.query_aspects import (
    aspects_supported,
    detect_aspects,
    refusal_for_unsupported_aspects,
)
from app.core.regions import FEDERAL_CODE, get_region
from app.llm.base import DEFAULT_MAX_TOKENS, LLMProviderError
from app.llm.factory import get_llm_provider
from app.llm.errors import friendly_llm_failure
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
from app.core.object_categories import categories_for_object, query_phrases_for_object
from app.vectorstore.retriever import hybrid_retrieve as retrieve

TOP_K_PER_QUERY = 20
MAX_CHUNKS_PER_REGION = 12
MAX_FEDERAL_CHUNKS = 12

# меньше запросов к эмбеддеру/Chroma → быстрее и дешевле по токенам LLM
_RETRIEVAL_QUERY_TEMPLATES: tuple[str, ...] = (
    "{bt}",
    "{bt} размещение парковка машино-места",
    "{bt} санитарно-защитная зона СанПиН",
    "{bt} пожарная безопасность эвакуация 123-ФЗ",
)


def _retrieval_queries(business_type: str) -> list[str]:
    canon = _canon_business_type(business_type)
    phrases = query_phrases_for_object(canon)
    return phrases[:10] or [t.format(bt=canon or business_type) for t in _RETRIEVAL_QUERY_TEMPLATES]

# короткие маркеры регионов больше не используем в UI — тематические эмодзи
_COMPARE_SIDE_EMOJI_A = "🔹"
_COMPARE_SIDE_EMOJI_B = "🔸"

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
    """Сначала извлекаем известный тип из фразы (без LLM); LLM — только если не вышло."""
    raw_text = (state.get("business_type") or "").strip()
    if not raw_text:
        return state

    if contains_forbidden_words(raw_text) or looks_like_prompt_injection(raw_text):
        return {**state, "error": FORBIDDEN_CONTENT_ERROR}

    if not looks_like_business_query(raw_text):
        return {**state, "error": INVALID_BUSINESS_TYPE_ERROR}

    # длинная фраза «требования к строительству автомойки…» — без вызова LLM
    extracted = extract_known_business_type(raw_text)
    if extracted:
        validation_error = _validate_business_type(extracted)
        if validation_error:
            return {**state, "error": validation_error}
        if extracted != raw_text.strip().lower().strip("«»\"'."):
            logger.info(f"тип бизнеса извлечён из фразы: «{raw_text}» → «{extracted}»")
            return {**state, "business_type": extracted, "business_type_raw": raw_text}
        return {**state, "business_type": extracted}

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
            temperature=0.0,
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

    cats = categories_for_object(business_type)
    return {
        **state,
        "business_type": business_type,
        "categories": cats,
        "transformed_query": state.get("transformed_query") or business_type,
    }


def query_transform(state: AgentState) -> AgentState:
    """Сленг/длинная фраза → канонический поисковый запрос (лёгкий LLM или без него)."""
    if state.get("error"):
        return state
    business_type = state.get("business_type") or ""
    raw = state.get("business_type_raw") or business_type
    # если уже извлекли короткий тип — transformation = тип + ключевые категории
    cats = state.get("categories") or categories_for_object(business_type)
    transformed = f"{business_type} " + " ".join(cats[:3])
    if len((raw or "").split()) <= 4:
        return {**state, "transformed_query": transformed.strip(), "categories": cats}

    try:
        provider = get_llm_provider()
        prompt = (
            "Переформулируй запрос проектировщика на официальный язык строительных нормативов РФ. "
            "Ответ — одна строка, без кавычек.\n"
            f"Запрос: {raw}"
        )
        out = provider.complete(
            "Ты нормализуешь поисковые запросы к НПА РФ.",
            prompt,
            max_tokens=64,
            temperature=0.0,
        )
        text = (out or "").strip().strip("«»\"'")
        if text:
            return {**state, "transformed_query": text, "categories": cats}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"query_transform fallback: {exc}")
    return {**state, "transformed_query": transformed.strip(), "categories": cats}


def rerank_retrieved(state: AgentState) -> AgentState:
    if state.get("error"):
        return state
    from app.agent.rerank import rerank_chunks

    query = state.get("transformed_query") or state.get("business_type") or ""
    new_state = {**state}
    for key in ("retrieved_a", "retrieved_b", "retrieved_federal"):
        chunks = list(state.get(key) or [])
        if chunks:
            # top-3 для LLM после hybrid top-N
            new_state[key] = rerank_chunks(query, chunks, top_n=min(3, len(chunks)))
    return new_state


def _chunk_mentions_business(chunk: RetrievedChunk, business_type: str) -> bool:
    needle = (business_type or "").strip().lower()
    if not needle:
        return False
    text = (chunk.text or "").lower()
    # морфология/синонимы: «автомойка» ↔ «автомоек», «склад» ↔ «складск…»
    stems = _BUSINESS_MENTION_STEMS.get(needle)
    if stems:
        return any(stem in text for stem in stems)
    if needle in text:
        return True
    # «автомойка» → «автомойк»; короткие типы — без обрезания
    stem = needle[:-1] if len(needle) > 5 and needle.endswith(("а", "я", "ы", "и")) else needle
    return len(stem) >= 4 and stem in text


# леммы/корни для boost retrieval (иначе «автомойка» не видит «автомоек» в таблице)
_BUSINESS_MENTION_STEMS: dict[str, tuple[str, ...]] = {
    "автомойка": ("автомойк", "автомоек", "моечн"),
    "автосервис": ("автосервис", "техническ", "станци"),
    "азс": ("азс", "автозаправ", "топливораздаточ"),
    "автозаправка": ("азс", "автозаправ", "топливораздаточ"),
    "склад": ("склад",),
    "складской комплекс": ("склад",),
    "складское помещение": ("склад",),
    "логистический центр": ("логистич", "склад"),
    "логистический комплекс": ("логистич", "склад"),
    "торговый центр": ("торгов", "торговый центр", "тц", "магазин"),
    "тц": ("торгов", "торговый центр", "тц"),
    "магазин": ("магазин", "торгов"),
    "кафе": ("кафе", "ресторан", "питан"),
    "ресторан": ("ресторан", "кафе", "питан"),
    "гостиница": ("гостиниц", "отел", "размещен"),
    "отель": ("гостиниц", "отел", "размещен"),
    "медицинский центр": ("медицин", "поликлиник", "больниц", "лпу"),
    "медцентр": ("медицин", "поликлиник", "больниц"),
    "поликлиника": ("поликлиник", "медицин", "больниц"),
    "офис": ("офис", "административ"),
    "офисное здание": ("офис", "административ"),
    "административное здание": ("офис", "административ"),
    "производство": ("производ", "завод", "цех"),
    "производственное здание": ("производ", "завод", "цех"),
    "цех": ("цех", "производ", "завод"),
    "завод": ("завод", "производ", "цех"),
}

# синонимы → канон для query phrases и tag-affinity (теги curated в каноне)
_RETRIEVAL_CANON: dict[str, str] = {
    "автозаправка": "азс",
    "тц": "торговый центр",
    "офисное здание": "офис",
    "административное здание": "офис",
    "ресторан": "кафе",
    "столовая": "кафе",
    "бар": "кафе",
    "магазин": "торговый центр",
    "супермаркет": "торговый центр",
    "отель": "гостиница",
    "хостел": "гостиница",
    "медцентр": "медицинский центр",
    "поликлиника": "медицинский центр",
    "больница": "медицинский центр",
    "аптека": "медицинский центр",
    "цех": "производство",
    "завод": "производство",
    "фабрика": "производство",
    "производственное здание": "производство",
    "складской комплекс": "склад",
    "складское помещение": "склад",
    "бизнес-центр": "офис",
    "логистический центр": "склад",
    "логистический комплекс": "склад",
}


def _canon_business_type(business_type: str) -> str:
    needle = (business_type or "").strip().lower()
    return _RETRIEVAL_CANON.get(needle, needle)


_LETTER_JUNK_SECTION = re.compile(
    r"^(?:"
    r"[а-яa-z]\d*/[а-яa-z]"  # а/в, б1/г — OCR-обломки списков
    r"|\d{1,2}/[а-яa-z]"  # 1/е, 2/ж
    r"|[а-яa-z]/\d{1,2}"  # а/1
    r")$",
    re.IGNORECASE,
)


def _section_rank_quality(section_number: str | None) -> int:
    """Выше = надёжнее цитата. Табличный мусор «1»/«300» и «1/е» — в хвост."""
    section = (section_number or "").strip()
    if not section:
        return 0
    if _LETTER_JUNK_SECTION.match(section):
        return 0
    # табл.pNN — автонумерация страниц PDF, не пункт НПА
    if section.lower().startswith("табл.p"):
        return 0
    if "/" in section or section.startswith("табл."):
        return 3
    if "." in section:
        return 2
    if section.isdigit() and int(section) >= 100:
        return 0
    if section.isdigit() and len(section) <= 2:
        return 0
    return 1


_GENERIC_FED_SECTIONS = frozenset(
    {
        "санпин/2.1",  # голое определение СЗЗ — главный crowding
    }
)
# широкие, но валидные якоря: не вытеснять 7.1.x, но оставлять в top-N
_BROAD_FED_SECTIONS = frozenset(
    {
        "санпин/4.1",
        "санпин/5.1",
        "123-фз/69",
    }
)


def _normalize_section_key(section: str | None) -> str:
    return (section or "").strip().replace(" ", "").lower()


def _is_curated_chunk(chunk: RetrievedChunk) -> bool:
    if (chunk.doc_type or "").upper() == "CURATED":
        return True
    return (chunk.id or "").startswith("curated::")


def _tags_match_business(tags: list[str], business_type: str) -> bool:
    needle = (business_type or "").strip().lower()
    if not needle or not tags:
        return False
    normalized = [t.strip().lower() for t in tags if t]
    if needle in normalized:
        return True
    stems = _BUSINESS_MENTION_STEMS.get(needle, ())
    for tag in normalized:
        if needle in tag or tag in needle:
            return True
        if stems and any(stem in tag for stem in stems):
            return True
    return False


def _resolve_retrieval_type(business_type: str) -> str:
    """Из длинной фразы юриста — канонический тип для queries/affinity."""
    from app.core.business_type import extract_known_business_type

    extracted = extract_known_business_type(business_type) or (business_type or "").strip()
    return _canon_business_type(extracted)


def _type_affinity(chunk: RetrievedChunk, business_type: str) -> int:
    """Приоритет чанков своего типа; чужой curated и голое определение СЗЗ — вниз.

    Без хаков по section_number (7.1.x / доп / azs) — только tags и текст.
    """
    needle = _resolve_retrieval_type(business_type)
    tags = list(chunk.tags or [])
    section_key = _normalize_section_key(chunk.section_number)
    if section_key in _GENERIC_FED_SECTIONS:
        return -2
    if tags:
        if _tags_match_business(tags, needle):
            if _is_curated_chunk(chunk):
                if section_key in _BROAD_FED_SECTIONS:
                    return 4
                # узкий тег-список — чуть выше multi-tag curated
                return 6 if len(tags) <= 2 else 5
            return 3
        if _is_curated_chunk(chunk):
            return -3
    if _chunk_mentions_business(chunk, needle) or _chunk_mentions_business(
        chunk, business_type
    ):
        return 2
    if section_key in _BROAD_FED_SECTIONS:
        return 1
    return 0


def _retrieve_for_region(
    business_type: str,
    region_code: str,
    *,
    max_chunks: int = MAX_CHUNKS_PER_REGION,
) -> list[RetrievedChunk]:
    """Multi-query hybrid retrieval; ranking по tags/doc_type из уже найденных чанков.

    Отдельный search только по CURATED (~36 точек) не используем: при golden,
    где expected = curated id, hit rate искусственно уходит в ~100%.
    """
    resolved = _resolve_retrieval_type(business_type)
    found: dict[str, RetrievedChunk] = {}

    queries = _retrieval_queries(resolved)
    raw = (business_type or "").strip()
    if raw and raw.lower() != resolved and raw not in queries:
        queries = [raw, *queries][:10]

    for query in queries:
        for chunk in retrieve(query, region_code=region_code, top_k=TOP_K_PER_QUERY):
            prev = found.get(chunk.id)
            if prev is None or chunk.distance < prev.distance:
                found[chunk.id] = chunk

    chunks = list(found.values())

    def _sort_key(chunk: RetrievedChunk) -> tuple[int, int, float]:
        return (
            -_type_affinity(chunk, resolved),
            -_section_rank_quality(chunk.section_number),
            chunk.distance,
        )

    chunks.sort(key=_sort_key)

    curated_hit = [
        c
        for c in chunks
        if _is_curated_chunk(c) and _type_affinity(c, resolved) >= 5
    ]
    if curated_hit:
        reserve = min(3, max_chunks, len(curated_hit))
        head = curated_hit[:reserve]
        head_ids = {c.id for c in head}
        tail = [c for c in chunks if c.id not in head_ids]
        chunks = head + tail

    return chunks[:max_chunks]


def retrieve_chunks(state: AgentState) -> AgentState:
    if state.get("error"):
        return state

    business_type = state["business_type"]
    chunks_a = _retrieve_for_region(business_type, state["region_a"])
    logger.info(f"регион A ({state['region_a']}): найдено {len(chunks_a)} чанков")

    chunks_federal = _retrieve_for_region(
        business_type, FEDERAL_CODE, max_chunks=MAX_FEDERAL_CHUNKS
    )
    logger.info(f"федеральный уровень: найдено {len(chunks_federal)} чанков")

    # отбрасываем табличный мусор перед LLM; если нечего опереться — честный отказ
    chunks_a = _filter_usable_chunks(chunks_a)
    chunks_federal = _filter_usable_chunks(chunks_federal)

    new_state: AgentState = {**state, "retrieved_a": chunks_a, "retrieved_federal": chunks_federal}

    if state.get("mode") == "compare" and state.get("region_b"):
        chunks_b = _filter_usable_chunks(_retrieve_for_region(business_type, state["region_b"]))
        logger.info(f"регион B ({state['region_b']}): найдено {len(chunks_b)} чанков")
        new_state["retrieved_b"] = chunks_b
    else:
        chunks_b = []

    if not chunks_a and not chunks_federal and not chunks_b:
        new_state["error"] = (
            "В доступных источниках (РНГП регионов, ГрК, СП 42, 123-ФЗ, СанПиН) "
            "не найдено проверяемых нормативных фрагментов по этому объекту. "
            "Рекомендуем сверить муниципальные ПЗЗ и отраслевые НПА напрямую."
        )
    elif _weak_retrieval_support(chunks_a, chunks_federal, chunks_b):
        new_state["error"] = (
            "Найдено слишком мало проверяемых нормативных фрагментов для надёжного "
            "ответа по этому объекту. Чтобы не давать неподтверждённые требования, "
            "система отказывается от вывода списка норм. "
            "Сверьте РНГП региона, 123-ФЗ и СанПиН в первоисточнике "
            "или уточните тип объекта / субъект РФ."
        )
    else:
        # узкий аспект запроса (напр. площадь участка) без опоры в чанках → отказ, не подмена темы
        raw_query = (state.get("business_type_raw") or business_type or "").strip()
        aspects = detect_aspects(raw_query)
        all_chunks = list(chunks_a) + list(chunks_federal) + list(chunks_b)
        if aspects and not aspects_supported(aspects, all_chunks):
            try:
                region_label = get_region(state["region_a"]).name_locative
            except Exception:
                region_label = "выбранном субъекте РФ"
            new_state["error"] = refusal_for_unsupported_aspects(
                aspects,
                business_type=state.get("business_type") or business_type,
                region_label=region_label,
            )

    return new_state


_MIN_USABLE_CHUNKS = 2


def _has_reliable_anchor(chunks: list[RetrievedChunk]) -> bool:
    """Curated или точечная нумерация с «/» / табл.N — опора лучше голых SP-пунктов."""
    for c in chunks:
        if _is_curated_chunk(c):
            return True
        sn = (c.section_number or "").strip()
        if "/" in sn or sn.startswith("табл."):
            return True
        if sn.count(".") >= 2:
            return True
    return False


def _weak_retrieval_support(
    chunks_a: list[RetrievedChunk],
    chunks_federal: list[RetrievedChunk],
    chunks_b: list[RetrievedChunk],
) -> bool:
    """Слабая опора: мало usable и нет надёжного якоря — лучше отказ, чем бред."""
    all_chunks = list(chunks_a) + list(chunks_federal) + list(chunks_b)
    if len(all_chunks) >= _MIN_USABLE_CHUNKS and _has_reliable_anchor(all_chunks):
        return False
    if len(all_chunks) >= 4:
        # много структурированных пунктов региона — считаем достаточным
        return False
    return len(all_chunks) < _MIN_USABLE_CHUNKS or not _has_reliable_anchor(all_chunks)


def _filter_usable_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Оставляет чанки с надёжной нумерацией; иначе LLM опирается на мусор и галлюцинирует."""
    if not chunks:
        return []
    good = [c for c in chunks if _section_rank_quality(c.section_number) >= 2]
    if good:
        return good
    mid = [c for c in chunks if _section_rank_quality(c.section_number) >= 1]
    return mid


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
                temperature=0.0,
            )
            logger.debug(f"сырой ответ LLM (extraction): {raw_answer}")
            extraction = parse_json_response(raw_answer, ExtractionResult)
        except (LLMProviderError, LLMParsingError) as exc:
            logger.error(f"не удалось получить extraction от LLM: {exc}")
            if isinstance(exc, LLMParsingError):
                logger.warning(f"сырой ответ LLM (extraction, parse fail): {str(exc)[:800]}")
            return {
                **state,
                "error": friendly_llm_failure(exc, mode="info"),
            }
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
            temperature=0.0,
        )
        logger.debug(f"сырой ответ LLM (compare): {raw_answer}")
        comparison = parse_json_response(raw_answer, ComparisonResult)
    except (LLMProviderError, LLMParsingError) as exc:
        logger.error(f"не удалось получить comparison от LLM: {exc}")
        if isinstance(exc, LLMParsingError):
            logger.warning(f"сырой ответ LLM (compare, parse fail): {str(exc)[:800]}")
        return {
            **state,
            "error": friendly_llm_failure(exc, mode="compare"),
        }

    region_a = get_region(state["region_a"])
    region_b = get_region(state["region_b"])
    allowed_chunks = (
        list(state.get("retrieved_a", []))
        + list(state.get("retrieved_b", []))
        + list(state.get("retrieved_federal", []))
    )
    grounded_commons = _filter_grounded_commons(comparison.common_requirements, allowed_chunks)
    chunks_a = list(state.get("retrieved_a", [])) + list(state.get("retrieved_federal", []))
    chunks_b = list(state.get("retrieved_b", [])) + list(state.get("retrieved_federal", []))
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
                "citation_a": _ground_optional_citation(diff.citation_a, chunks_a),
                "citation_b": _ground_optional_citation(diff.citation_b, chunks_b),
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
        f"Требования к объекту капитального строительства "
        f"«{_esc(business_type)}» в {region_locative}."
    )


def _greeting_for_comparison(business_type: str, region_a_locative: str, region_b_locative: str) -> str:
    return (
        f"Сравнение требований к объекту капитального строительства "
        f"«{_esc(business_type)}» в {region_a_locative} и в {region_b_locative}."
    )


def _normalize_citation(citation: str) -> str:
    cleaned = (citation or "").strip().strip("[]()«»\"'")
    while cleaned:
        lowered = cleaned.lower()
        matched = False
        for prefix in _CITATION_PREFIXES:
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix):].lstrip(" .;:")
                cleaned = cleaned.strip().strip("[]()«»\"'")
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
    normalized_compact = normalized.replace(" ", "")
    for chunk in chunks:
        section = (chunk.section_number or "").strip()
        if not section:
            continue
        # точное совпадение всегда ок
        if section == normalized or section.replace(" ", "") == normalized_compact:
            return True
        # префиксное совпадение только для «настоящих» пунктов с точкой
        # (иначе section="1" пропускает выдуманные «1.5.153», «15» и т.п.)
        if "." in section and (
            section.startswith(normalized + ".") or normalized.startswith(section + ".")
        ):
            return True
        # curated ID: «123-ФЗ/6», «СанПиН/7.1.3» — модель может вернуть суффикс или полный id
        if "/" in section:
            prefix, suffix = section.rsplit("/", 1)
            section_compact = section.replace(" ", "")
            if normalized_compact == section_compact:
                return True
            # «7.1.3» для СанПиН/7.1.3 — ок; голый «6» для 123-ФЗ/6 — нет
            if normalized == suffix and (len(suffix) > 1 or "." in suffix):
                return True
            if normalized_compact.endswith("/" + suffix):
                return True
            if prefix.lower() in normalized.lower() and suffix in normalized:
                return True
            # «СанПиН 2.2.1/2.1.1.1200-03» без номера пункта — не матчим к конкретному чанку
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


def _ground_optional_citation(citation: str, chunks: list[RetrievedChunk]) -> str:
    """Пустой/«пункт не указан» оставляем; выдуманный номер обнуляем."""
    raw = (citation or "").strip()
    if not raw or raw.lower() in {"пункт не указан", "без номера", "n/a", "-", "—"}:
        return ""
    if _citation_matches_chunks(raw, chunks):
        return raw
    logger.warning(f"отброшена citation без опоры на чанки: {raw!r}")
    return ""


def _punkt_label(citation: str) -> str:
    normalized = _normalize_citation(citation)
    if not normalized or normalized.lower() in {"пункт не указан", "без номера", "n/a", "-", "—"}:
        return "номер пункта в доступных фрагментах не приведён"
    # curated id уже содержит документ: «СанПиН/7.1.3», «123-ФЗ/69»
    if "/" in normalized:
        return normalized
    return f"п. {normalized}"


def _full_npa_for_item(citation: str, source_level: str, region_code: str) -> str:
    if source_level == "федеральный":
        return full_federal_cite_from_citation(citation)
    return get_region(region_code).document_title


def _source_url_for_item(citation: str, source_level: str, region_code: str) -> str:
    if source_level == "федеральный":
        return federal_source_url(citation)
    return (get_region(region_code).source_url or "").strip()


def _html_link(url: str, label: str) -> str:
    safe_url = html.escape(url, quote=True)
    return '<a href="{}">{}</a>'.format(safe_url, _esc(label))


def _format_item_source(citation: str, source_level: str, region_code: str) -> str:
    """Полное название НПА + пункт + ссылка на первоисточник (HTML для Telegram)."""
    npa = _full_npa_for_item(citation, source_level, region_code)
    level = "федеральный" if source_level == "федеральный" else "региональный"
    punkt = _punkt_label(citation)
    url = _source_url_for_item(citation, source_level, region_code)
    parts = f"({_esc(level)}: {_esc(npa)}; {_esc(punkt)}"
    if url:
        return f"{parts}; {_html_link(url, 'открыть первоисточник')})"
    return f"{parts})"


def _format_compare_side(
    region_code: str,
    value: str,
    citation: str,
    source_level: str,
    side_emoji: str,
) -> str:
    if source_level == "федеральный":
        npa = full_federal_cite_from_citation(citation)
        url = federal_source_url(citation)
    else:
        region = get_region(region_code)
        npa = region.document_title
        url = (region.source_url or "").strip()
    region = get_region(region_code)
    cite = f"{_esc(npa)}; {_esc(_punkt_label(citation))}"
    if url:
        cite = f"{cite}; {_html_link(url, 'первоисточник')}"
    return (
        f"  {side_emoji} <b>{_esc(region.display_name)}</b> "
        f"({cite}): {_esc(_humanize_missing_value(value))}"
    )


def audit_sections_from_state(state: AgentState) -> list[dict[str, str | None]]:
    """Сжатый audit trail retrieval для QueryLog (без полного текста чанков)."""
    rows: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for key in ("retrieved_a", "retrieved_b", "retrieved_federal"):
        for chunk in state.get(key) or []:
            if chunk.id in seen:
                continue
            seen.add(chunk.id)
            rows.append(
                {
                    "chunk_id": chunk.id,
                    "region_code": chunk.region_code,
                    "section_number": chunk.section_number,
                }
            )
    return rows


def _render_item_bullets(items: list[RequirementItem], region_code: str) -> list[str]:
    lines: list[str] = []
    specific_items = [item for item in items if item.is_specific]
    general_items = [item for item in items if not item.is_specific]
    if specific_items and general_items:
        for item in specific_items:
            source = _format_item_source(item.citation, item.source_level, region_code)
            lines.append(f"• {_esc(item.description)} {source}")
        lines.append("Плюс действуют общие нормы:")
        for item in general_items:
            source = _format_item_source(item.citation, item.source_level, region_code)
            lines.append(f"• {_esc(item.description)} {source}")
        return lines

    ordered = specific_items + general_items if specific_items else general_items
    for item in ordered:
        source = _format_item_source(item.citation, item.source_level, region_code)
        lines.append(f"• {_esc(item.description)} {source}")
    return lines


def _render_level_by_category(
    items: list[RequirementItem],
    region_code: str,
    business_type: str,
) -> list[str]:
    lines: list[str] = []
    groups = _group_by_category(items)
    for category in get_settings().requirement_categories:
        category_items = groups.get(category) or []
        if not category_items:
            continue
        lines.append(f"\n<b>{_category_label(category)}</b>")
        specific = [item for item in category_items if item.is_specific]
        general = [item for item in category_items if not item.is_specific]
        if not specific and general:
            lines.append(
                f"Специальных требований к «{_esc(business_type)}» здесь нет, "
                f"но применяются общие нормы:"
            )
        lines.extend(_render_item_bullets(category_items, region_code))
    return lines


def _humanize_missing_value(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return _MISSING_REGION_VALUE
    lowered = cleaned.lower()
    if "не указано" in lowered or "отсутств" in lowered or "фрагментах" in lowered:
        # если модель пишет «не указано» разными словами — сводим к одной фразе
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
    regional_items = [item for item in extraction.items if item.source_level != "федеральный"]
    federal_items = [item for item in extraction.items if item.source_level == "федеральный"]
    has_regional = bool(regional_items)
    has_federal = bool(federal_items)

    regional_npa = region.document_title
    federal_npa_names = sorted(
        {
            full_federal_cite_from_citation(item.citation)
            for item in federal_items
        }
    )

    lines = [
        f"<b>{_greeting_for_info(extraction.business_type, region.name_locative)}</b>",
        f"🏛 Правовое регулирование (регион): {_esc(regional_npa)} "
        f"(проверено {region.last_verified})",
    ]
    if region.source_url:
        lines.append(
            "🔗 Региональный первоисточник: "
            + _html_link(region.source_url, "открыть документ")
        )
    lines.append(
        f"📜 Федеральный уровень: {_esc(sp_label)}; при наличии в источниках — также "
        f"{_esc(expand_npa_label('123-ФЗ'))} и {_esc(expand_npa_label('СанПиН'))}."
    )

    lines.append("\n<b>Наличие требований по объекту</b>")
    if has_regional:
        lines.append(
            f"• Региональные: <b>найдены</b> — {_esc(regional_npa)}."
        )
    else:
        lines.append(
            "• Региональные: <b>не найдены</b> в доступном РНГП/ТСН по данному объекту."
        )
    if has_federal:
        named = "; ".join(federal_npa_names) if federal_npa_names else sp_label
        lines.append(f"• Федеральные: <b>найдены</b> — {_esc(named)}.")
    else:
        lines.append(
            "• Федеральные: <b>не найдены</b> в объёме СП 42, 123-ФЗ и СанПиН "
            "по данному объекту."
        )

    lines.append("\n<b>Региональный уровень</b>")
    if has_regional:
        lines.extend(
            _render_level_by_category(regional_items, extraction.region_code, extraction.business_type)
        )
    else:
        lines.append(
            "Специальные требования в региональном нормативе не установлены."
        )

    lines.append("\n<b>Федеральный уровень</b>")
    if has_federal:
        if has_regional:
            lines.append("Дополнительно применяются федеральные нормы:")
        else:
            lines.append(
                "На региональном уровне требования не установлены — "
                "применяются федеральные нормы:"
            )
        lines.extend(
            _render_level_by_category(federal_items, FEDERAL_CODE, extraction.business_type)
        )
    else:
        lines.append(
            "В объёме доступных федеральных источников (СП 42, 123-ФЗ, СанПиН) "
            "специальных требований к объекту не найдено."
        )

    if not has_regional and not has_federal:
        lines.append(
            "\nИтого: в доступных источниках требования не найдены ни на "
            "региональном, ни на федеральном уровне. Имеет смысл сверить "
            "муниципальные ПЗЗ и отраслевые НПА отдельно."
        )

    lines.append(format_additional_checks_block(extraction.business_type))
    return "\n".join(lines)


def _render_comparison(comparison: ComparisonResult) -> str:
    region_a = get_region(comparison.region_a)
    region_b = get_region(comparison.region_b)
    sp_label = federal_sp42_label()
    lines = [
        f"<b>{_greeting_for_comparison(comparison.business_type, region_a.name_locative, region_b.name_locative)}</b>",
        f"🏛 {region_a.display_name} — правовое регулирование: {_esc(region_a.document_title)} "
        f"(проверено {region_a.last_verified})",
        f"⚖ {region_b.display_name} — правовое регулирование: {_esc(region_b.document_title)} "
        f"(проверено {region_b.last_verified})",
        f"📜 Федеральные нормы (применяются при отсутствии региональных): {_esc(sp_label)}.",
        f"\n{_esc(comparison.overall_summary)}",
    ]

    commons = [item for item in (comparison.common_requirements or []) if _is_concrete_common(item)]
    differences = list(comparison.differences or [])

    lines.append("\n<b>Как читать сравнение</b>")
    if differences and commons:
        lines.append(
            "Сначала — <b>только различия</b> между субъектами; затем отдельный блок "
            "совпадающих требований (одинаковые нормы или общая опора на федеральный "
            "уровень). Вне этих блоков иных выводов в ответе нет."
        )
    elif differences and not commons:
        lines.append(
            "Ниже перечислены <b>различия</b>. Совпадающих конкретных требований "
            "в доступных источниках не выявлено."
        )
    elif commons and not differences:
        lines.append(
            "Различий не обнаружено: ниже — требования, которые <b>совпадают</b> "
            "или одинаково опираются на федеральные нормы."
        )
    else:
        lines.append(
            "Ни различий, ни совпадающих конкретных требований в доступных "
            "источниках не выявлено."
        )

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
                    _format_compare_side(
                        comparison.region_a,
                        diff.region_a_value,
                        diff.citation_a,
                        diff.source_level,
                        _COMPARE_SIDE_EMOJI_A,
                    )
                )
                lines.append(
                    _format_compare_side(
                        comparison.region_b,
                        diff.region_b_value,
                        diff.citation_b,
                        diff.source_level,
                        _COMPARE_SIDE_EMOJI_B,
                    )
                )
                diff_number += 1
    else:
        lines.append("\n<b>Чем отличаются</b>\nРазличий не обнаружено.")

    if commons:
        lines.append("\n<b>Что совпадает</b>")
        lines.append(
            "Эти требования совпадают или одинаково опираются на федеральные нормы:"
        )
        for index, item in enumerate(commons, start=1):
            source_code = FEDERAL_CODE if item.source_level == "федеральный" else comparison.region_a
            source = _format_item_source(item.citation, item.source_level, source_code)
            federal_note = f" (по {sp_label})" if item.source_level == "федеральный" else ""
            lines.append(f"{index}. {_esc(item.description)}{federal_note} {source}")
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
        prefix = f"<i>Тип объекта: «{_esc(state['business_type'])}»</i>\n\n"

    if state["mode"] == "info" and state.get("extraction"):
        body = _render_extraction(state["extraction"])
    elif state["mode"] == "compare" and state.get("comparison"):
        body = _render_comparison(state["comparison"])
    else:
        return {**state, "response_text": "Не удалось сформировать ответ по имеющимся данным."}

    from app.agent.guardrail import build_refusal, claim_numbers_supported

    context_chunks = (
        list(state.get("retrieved_a") or [])
        + list(state.get("retrieved_b") or [])
        + list(state.get("retrieved_federal") or [])
    )
    # шапка с реквизитами НПА даёт ложные срабатывания (даты постановлений)
    guardrail_plain = re.sub(r"<[^>]+>", "", body)
    guardrail_plain = "\n".join(
        line
        for line in guardrail_plain.splitlines()
        if not line.lstrip().startswith(("🏛", "📜", "⚖"))
        and "Правовое регулирование" not in line
    )
    if context_chunks and not claim_numbers_supported(guardrail_plain, context_chunks):
        logger.warning("guardrail заблокировал ответ")
        return {
            **state,
            "guardrail_blocked": True,
            "response_text": prefix + build_refusal(context_chunks) + DISCLAIMER_TEXT,
        }

    return {
        **state,
        "guardrail_blocked": False,
        "response_text": prefix + body + DISCLAIMER_TEXT,
    }
