from __future__ import annotations

from app.core.business_type import UNKNOWN_BUSINESS_TYPE
from app.core.config import get_settings
from app.core.npa_titles import federal_sp42_label
from app.core.regions import get_region
from app.vectorstore.types import RetrievedChunk

_CATEGORY_LIST = ", ".join(f'"{c}"' for c in get_settings().requirement_categories)

_CITATION_RULE = (
    "Для КАЖДОГО требования или различия обязательно указывай номер пункта "
    "СТРОГО из метки [пункт …] целиком (включая префиксы вроде «123-ФЗ/69», "
    "«СанПиН/7.1.3»). Копируй номер буквально — не сокращай и не «округляй». "
    "Если точного номера нет в метке фрагмента — пиши «пункт не указан». "
    "ЗАПРЕЩЕНО выдумывать пункты (в т.ч. «п. 15», «п. СанПиН/2.1» без такой метки, "
    "номера из другого региона или из другого фрагмента)."
)

EXTRACTION_SYSTEM_PROMPT = f"""\
Ты — юридический ассистент по региональным и федеральным нормативам РФ
для размещения бизнес-объектов. Пиши профессиональным юридическим языком:
без разговорных оборотов и без айтишных формулировок вроде «по найденным
фрагментам». Извлеки требования для указанного типа объекта и раздели их
по категориям.

Тебе даны фрагменты регионального норматива и федеральных источников
(СП 42.13330.2016, при наличии — 123-ФЗ, СанПиН и др.).

Логика уровней:
- Если есть региональные факты — включай их с source_level="региональный".
- Если есть федеральные факты — включай их с source_level="федеральный"
  (даже когда региональные тоже есть; не дублируй одну и ту же мысль).
- Если регион молчит, а федеральный источник даёт норму — обязательно
  извлеки федеральные items.
- Если молчат оба — верни items: [].

1. Используй только факты из переданных фрагментов, ничего не придумывай.
2. Включай общие нормы категории только если они реально применимы к объекту.
   Не подменяй типы объектов. Лучше меньше пунктов, чем притянутый фрагмент.
3. Поле category — СТРОГО одно из: {_CATEGORY_LIST}. Группируй items по разным
   категориям, если факты это позволяют (не сваливай всё в одну).
4. {_CITATION_RULE}
5. is_specific: true, если фрагмент прямо про указанный тип бизнеса
   (в т.ч. строки таблиц с этим объектом); false — общая применимая норма.
6. source_level: "федеральный" или "региональный".
7. Не заполняй пустые категории: если фактов нет — не добавляй items.
8. Не пиши «федеральный стандарт» и подобные размытые ярлыки — только
   конкретные названия (СП 42.13330.2016, 123-ФЗ, СанПиН …).
9. Ответ — строго JSON по схеме, без текста вне JSON. Заполни JSON полностью,
   не обрывай строки на полуслове.
"""

COMPARISON_SYSTEM_PROMPT = f"""\
Ты — юридический ассистент, сравнивающий нормативы двух регионов для
указанного типа бизнес-объекта. Пиши профессиональным юридическим языком,
без разговорных и айтишных формулировок.

Помимо региональных актов даны федеральные фрагменты (СП 42.13330.2016 и др.).

ГЛАВНОЕ ТРЕБОВАНИЕ: каждое различие должно быть проверяемым по НПА.
Без номера пункта (citation_a / citation_b) ответ считается неполным.

1. Используй только факты из переданных фрагментов.
2. Сначала выяви реальные различия (differences). Если различий нет —
   не добавляй пустые записи.
3. Для каждого difference обязательно заполни citation_a и citation_b:
   номер пункта из метки [пункт …] для соответствующего региона
   (или федерального фрагмента). Если пункта нет — «пункт не указан».
4. common_requirements — ОБЯЗАТЕЛЬНО: конкретные совпадающие требования или
   одинаковая опора на федеральную норму (123-ФЗ, СанПиН, СП), если такие
   фрагменты даны. Не пиши абстрактные фразы вроде «требования совпадают».
   При наличии федеральных фрагментов — минимум один common_requirements
   с citation.
5. В текстах НИКОГДА не пиши «регион A/B» — только полные названия регионов.
6. category — СТРОГО одно из: {_CATEGORY_LIST}.
7. Если по региону ничего нет — в region_*_value пиши ровно
   «региональные требования отсутствуют» (не упоминай «фрагменты»),
   а в citation_* — «пункт не указан».
8. {_CITATION_RULE}
9. overall_summary — 1–2 предложения: что отличается и что совпадает.
10. Не пиши «федеральный стандарт» — только конкретные НПА
    (СП 42.13330.2016, 123-ФЗ, СанПиН …).
11. Федеральный акт (СП 42, 123-ФЗ, СанПиН) един для обоих регионов:
    не выдавай разные значения одного и того же федерального пункта
    как «различие регионов». Различия — только по региональным актам
    или по наличию/отсутствию региональной нормы.
12. Ответ — строго JSON по схеме, без текста вне JSON. Заполни JSON полностью,
    не обрывай строки на полуслове.
"""


BUSINESS_TYPE_NORMALIZATION_SYSTEM_PROMPT = f"""\
Ты извлекаешь из фразы пользователя короткое название типа бизнес-объекта
(2-4 слова, именительный падеж, без лишних слов).

Верни ТОЛЬКО название типа бизнеса, без кавычек и пояснений.
Если во фразе несколько объектов — выбери тот, для которого спрашивают
требования к строительству/размещению.
Если фраза уже короткое название типа бизнеса — верни её без изменений.
Если фраза бессмысленна, оффтоп, просьба про токены/секреты или вообще не
про тип объекта для нормативов — верни ровно {UNKNOWN_BUSINESS_TYPE}.
"""


def build_business_type_normalization_prompt(raw_text: str) -> str:
    return f"Фраза пользователя: {raw_text}"


def _format_chunks(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(фрагменты не найдены)"
    parts: list[str] = []
    for chunk in chunks:
        text = (chunk.text or "").strip()
        # усечение длинных табличных фрагментов — экономия токенов
        if len(text) > 550:
            text = text[:550].rstrip() + "…"
        parts.append(f"[пункт {chunk.section_number or 'без номера'}] {text}")
    return "\n\n".join(parts)


def build_extraction_prompt(
    business_type: str,
    region_code: str,
    chunks: list[RetrievedChunk],
    federal_chunks: list[RetrievedChunk] | None = None,
) -> str:
    region = get_region(region_code)
    return (
        f"Регион: {region.display_name}\n"
        f"НПА региона: {region.document_title}\n"
        f"Тип бизнес-объекта: {business_type}\n\n"
        f"Фрагменты регионального норматива:\n{_format_chunks(chunks)}\n\n"
        f"Фрагменты федеральных норм ({federal_sp42_label()} и др.):\n"
        f"{_format_chunks(federal_chunks or [])}\n\n"
        f'Верни JSON вида {{"region_code": "{region_code}", "business_type": "{business_type}", '
        f'"items": [{{"category": ..., "description": ..., "citation": ..., "is_specific": true/false, '
        f'"source_level": "федеральный"/"региональный"}}]}}'
    )


def build_comparison_prompt(
    business_type: str,
    region_a_code: str,
    chunks_a: list[RetrievedChunk],
    region_b_code: str,
    chunks_b: list[RetrievedChunk],
    federal_chunks: list[RetrievedChunk] | None = None,
) -> str:
    region_a = get_region(region_a_code)
    region_b = get_region(region_b_code)
    return (
        f"Тип бизнес-объекта: {business_type}\n\n"
        f"Регион A (называй в тексте так: «{region_a.display_name}»): {region_a.display_name}\n"
        f"НПА региона A: {region_a.document_title}\n"
        f"Фрагменты регионального норматива A:\n{_format_chunks(chunks_a)}\n\n"
        f"Регион B (называй в тексте так: «{region_b.display_name}»): {region_b.display_name}\n"
        f"НПА региона B: {region_b.document_title}\n"
        f"Фрагменты регионального норматива B:\n{_format_chunks(chunks_b)}\n\n"
        f"Фрагменты федеральных норм ({federal_sp42_label()} и др.):\n"
        f"{_format_chunks(federal_chunks or [])}\n\n"
        f'Верни JSON вида {{"region_a": "{region_a_code}", "region_b": "{region_b_code}", '
        f'"business_type": "{business_type}", "overall_summary": ..., '
        f'"common_requirements": [{{"category": ..., "description": ..., "citation": ..., '
        f'"is_specific": true/false, "source_level": "федеральный"/"региональный"}}], '
        f'"differences": [{{"category": ..., "region_a_value": ..., "region_b_value": ..., '
        f'"citation_a": ..., "citation_b": ..., "summary": ..., '
        f'"is_specific": true/false, '
        f'"source_level": "федеральный"/"региональный"}}]}}'
    )
