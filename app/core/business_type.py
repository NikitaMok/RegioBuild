from __future__ import annotations

import difflib
import re

# ответ нормализации, если фраза не про тип бизнес-объекта
UNKNOWN_BUSINESS_TYPE = "НЕИЗВЕСТНО"

# опечатки вроде «Медьцынский центр» → «медицинский центр»
FUZZY_MATCH_CUTOFF = 0.65
MAX_QUERY_LENGTH = 200

_TYPO_ALIASES: dict[str, str] = {
    "медьцынский центр": "медицинский центр",
    "медецинский центр": "медицинский центр",
    "медицинскй центр": "медицинский центр",
    "автомойкка": "автомойка",
    "автосервисз": "автосервис",
}

_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior)\s+instructions", re.I),
    re.compile(r"забудь\s+(все|предыдущ)", re.I),
    re.compile(r"system\s*prompt", re.I),
    re.compile(r"<\s*/?\s*system\s*>", re.I),
)

# явный список запрещённого: секреты, атаки, оффтоп про доступы
FORBIDDEN_WORDS: tuple[str, ...] = (
    "токен",
    "token",
    "api key",
    "apikey",
    "пароль",
    "password",
    "passwd",
    "секрет",
    "secret",
    "credentials",
    "credential",
    "скинь",
    "взлом",
    "хак",
    "hack",
    "exploit",
    "кредитн",
    "cvv",
    "private key",
    "приватный ключ",
    "ssh key",
    "bearer",
)

# известные типы объектов для РНГП — после нормализации тип должен попасть сюда
KNOWN_BUSINESS_TYPES: tuple[str, ...] = (
    "автомойка",
    "автосервис",
    "автостоянка",
    "парковка",
    "стоянка",
    "кафе",
    "ресторан",
    "столовая",
    "бар",
    "склад",
    "логистический центр",
    "логистический комплекс",
    "офис",
    "офисное здание",
    "административное здание",
    "медицинский центр",
    "медцентр",
    "поликлиника",
    "больница",
    "аптека",
    "торговый центр",
    "тц",
    "магазин",
    "супермаркет",
    "рынок",
    "гостиница",
    "отель",
    "хостел",
    "школа",
    "детский сад",
    "фитнес",
    "спортзал",
    "спортивный комплекс",
    "салон красоты",
    "парикмахерская",
    "салон",
    "производственное здание",
    "цех",
    "завод",
    "фабрика",
    "табачный магазин",
    "автозаправка",
    "азс",
    "банк",
    "отделение банка",
    "кинотеатр",
    "театр",
    "музей",
    "библиотека",
    "складской комплекс",
    "многоквартирный дом",
    "жилой дом",
    "бизнес-центр",
    "коворкинг",
    "складское помещение",
    "торговая точка",
    "павильон",
)

_SHORT_FUNCTION_WORDS = frozenset({
    "в", "во", "на", "с", "со", "к", "по", "за", "от", "до", "из", "у",
    "и", "а", "но", "или", "для", "при", "об", "не", "ни", "же", "ли",
    "бы", "то", "что", "как", "так", "это", "возле", "около", "тц", "тд",
    "м", "г", "ул", "д",
})


def contains_forbidden_words(text: str) -> bool:
    lower = (text or "").lower()
    return any(word in lower for word in FORBIDDEN_WORDS)


def fuzzy_match_business_type(value: str) -> str | None:
    """Ближайший известный тип при опечатке; None — если совпадений нет."""
    text = (value or "").strip().lower().strip("«»\"'.")
    if not text:
        return None
    if text in _TYPO_ALIASES:
        return _TYPO_ALIASES[text]
    matches = difflib.get_close_matches(
        text,
        KNOWN_BUSINESS_TYPES,
        n=1,
        cutoff=FUZZY_MATCH_CUTOFF,
    )
    return matches[0] if matches else None


def is_known_business_type(value: str) -> bool:
    """Проверяет, что нормализованный тип похож на один из известных объектов."""
    text = (value or "").strip().lower().strip("«»\"'.")
    if not text:
        return False
    if extract_known_business_type(text) is not None:
        return True
    for known in KNOWN_BUSINESS_TYPES:
        if known == text or known in text or text in known:
            return True
    return fuzzy_match_business_type(text) is not None


def resolve_business_type(value: str) -> str:
    """Канонический тип: точное/подстрочное совпадение или fuzzy."""
    text = (value or "").strip().lower().strip("«»\"'.")
    if not text:
        return text
    extracted = extract_known_business_type(text)
    if extracted:
        return extracted
    return fuzzy_match_business_type(text) or text


# корни для падежей: «автомойки» / «автомоек» → «автомойка»
_BUSINESS_TYPE_STEMS: dict[str, tuple[str, ...]] = {
    "автомойка": ("автомойк", "автомоек", "моечн"),
    "автосервис": ("автосервис",),
    "азс": ("азс", "автозаправ"),
    "автозаправка": ("азс", "автозаправ"),
    "склад": ("склад",),
    "складской комплекс": ("складск",),
    "складское помещение": ("складск",),
    "логистический центр": ("логистич",),
    "логистический комплекс": ("логистич",),
    "торговый центр": ("торговый центр", "торгов"),
    "магазин": ("магазин",),
    "кафе": ("кафе",),
    "ресторан": ("ресторан",),
    "гостиница": ("гостиниц",),
    "отель": ("отел",),
    "медицинский центр": ("медицинск", "медцентр"),
    "медцентр": ("медцентр", "медицинск"),
    "поликлиника": ("поликлиник",),
    "офис": ("офис",),
    "офисное здание": ("офисн",),
    "производственное здание": ("производственн",),
    "цех": ("цех",),
    "завод": ("завод",),
}


def extract_known_business_type(text: str) -> str | None:
    """Достаёт известный тип из длинной фразы, в т.ч. в падежах («автомойки»)."""
    lower = (text or "").strip().lower()
    if not lower:
        return None

    # сначала длинные названия, чтобы «медицинский центр» победил «центр»
    for known in sorted(KNOWN_BUSINESS_TYPES, key=len, reverse=True):
        if known in lower:
            return known

    for known, stems in _BUSINESS_TYPE_STEMS.items():
        if any(len(stem) >= 3 and stem in lower for stem in stems):
            return known

    for known in sorted(KNOWN_BUSINESS_TYPES, key=len, reverse=True):
        stem = known[:-1] if len(known) > 5 and known[-1] in "аяыи" else known
        if len(stem) >= 5 and stem in lower:
            return known
    return None


def looks_like_prompt_injection(text: str) -> bool:
    cleaned = text or ""
    return any(pattern.search(cleaned) for pattern in _INJECTION_PATTERNS)


def looks_like_business_query(text: str) -> bool:
    """Грубая проверка до LLM: отсекает оффтоп и явно битый ввод."""
    cleaned = (text or "").strip()
    if len(cleaned) < 2 or len(cleaned) > MAX_QUERY_LENGTH:
        return False

    if contains_forbidden_words(cleaned):
        return False

    if looks_like_prompt_injection(cleaned):
        return False

    letters = sum(ch.isalpha() for ch in cleaned)
    if letters < 2 or letters / max(len(cleaned), 1) < 0.4:
        return False

    words = re.findall(r"[а-яёa-z]+", cleaned.lower())
    # обрыв слова ищем только в коротких вводах («Парко вка возле тц»)
    if len(words) <= 5:
        for left, right in zip(words, words[1:]):
            if left in _SHORT_FUNCTION_WORDS or right in _SHORT_FUNCTION_WORDS:
                continue
            if 3 <= len(left) <= 5 and 2 <= len(right) <= 3:
                return False

    return True


def is_unknown_business_type(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip().strip("«»\"'.").upper()
    return normalized in {UNKNOWN_BUSINESS_TYPE, "UNKNOWN", "N/A", "NONE"}
