from __future__ import annotations

import re

# ответ нормализации, если фраза не про тип бизнес-объекта
UNKNOWN_BUSINESS_TYPE = "НЕИЗВЕСТНО"

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


def is_known_business_type(value: str) -> bool:
    """Проверяет, что нормализованный тип похож на один из известных объектов."""
    text = (value or "").strip().lower().strip("«»\"'.")
    if not text:
        return False
    for known in KNOWN_BUSINESS_TYPES:
        if known == text or known in text or text in known:
            return True
    return False


def looks_like_business_query(text: str) -> bool:
    """Грубая проверка до LLM: отсекает оффтоп и явно битый ввод."""
    cleaned = (text or "").strip()
    if len(cleaned) < 2:
        return False

    if contains_forbidden_words(cleaned):
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
