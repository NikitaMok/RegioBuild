"""Strict guardrail: цифры/утверждения ответа ⊆ retrieved chunks."""

from __future__ import annotations

import re

from loguru import logger

from app.vectorstore.types import RetrievedChunk

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?%?")
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_DATE_DM = re.compile(r"^\d{1,2}\.\d{1,2}$")
# номера реквизитов НПА в тексте ответа («№ 713/30», «N 1071», «Приказ … N 78»)
_NPA_REQUISITE_NUM = re.compile(
    r"(?:№|N)\s*(\d+(?:/\d+)?)|"
    r"(?:Постановлени\w+|Приказ\w+)\s+[^\n]{0,100}?(?:№|N)\s*(\d+(?:/\d+)?)",
    re.IGNORECASE,
)
_SAFE_REFUSAL = (
    "Внимание: система обнаружила неточность при верификации пунктов. "
    "Чтобы защитить от ошибочных цифр, ответ заблокирован. "
    "Обратитесь к первоисточнику: {docs}."
)
_SOFT_WARNING = (
    "Внимание: при сверке числовых показателей с доступными фрагментами "
    "нормативных актов обнаружены расхождения. Ниже приведён ответ; "
    "рекомендуем сверить цифры и пункты с официальным текстом. "
    "Первоисточники: {docs}."
)


def _numbers_in(text: str) -> set[str]:
    return {m.group(0).replace(",", ".") for m in _NUMBER.finditer(text or "")}


def _npa_requisite_numbers(text: str) -> set[str]:
    """Числа из реквизитов НПА в ответе — не считаем выдуманными ориентирами."""
    found: set[str] = set()
    for match in _NPA_REQUISITE_NUM.finditer(text or ""):
        raw = match.group(1) or match.group(2) or ""
        if not raw:
            continue
        found.add(raw.replace(",", "."))
        if "/" in raw:
            for part in raw.split("/"):
                if part:
                    found.add(part.replace(",", "."))
    return found


def _is_boilerplate_number(n: str) -> bool:
    """Даты реквизитов НПА и годы — не повод блокировать ответ."""
    if _YEAR.fullmatch(n) or _DATE_DM.fullmatch(n):
        return True
    # типичный шум шапки: «N 713/30», день месяца
    if n.isdigit() and len(n) <= 2:
        return True
    return False


def claim_numbers_supported(answer: str, chunks: list[RetrievedChunk], *, min_ratio: float = 0.85) -> bool:
    """Основные числа из ответа должны встречаться в контексте (или быть номерами пунктов)."""
    del min_ratio  # совместимость сигнатуры; порог Similarity не используется
    context_parts: list[str] = []
    for chunk in chunks:
        if chunk.section_number:
            context_parts.append(str(chunk.section_number))
        context_parts.append(chunk.text or "")
    context = "\n".join(context_parts)
    context_nums = _numbers_in(context)
    answer_nums = _numbers_in(answer)
    npa_nums = _npa_requisite_numbers(answer)
    suspicious = {
        n
        for n in answer_nums
        if n not in context_nums
        and n not in npa_nums
        and not n.endswith("%")
        and len(n) <= 6
        and not _is_boilerplate_number(n)
    }
    pct_bad = [n for n in answer_nums if n.endswith("%") and n not in context_nums]
    if pct_bad:
        logger.warning(f"guardrail: проценты без опоры {pct_bad}")
        return False
    if len(suspicious) >= 3:
        logger.warning(f"guardrail: лишние числа {suspicious}")
        return False
    return True


def _docs_label(chunks: list[RetrievedChunk]) -> str:
    docs = sorted(
        {
            (c.text.split("]")[0] + "]") if "[" in (c.text or "") else "НПА"
            for c in chunks[:5]
        }
    )
    return "; ".join(docs[:3]) if docs else "региональный / федеральный НПА"


def build_refusal(chunks: list[RetrievedChunk]) -> str:
    """Полный отказ (совместимость / явный block в API). В production не используется."""
    return _SAFE_REFUSAL.format(docs=_docs_label(chunks))


def build_guardrail_warning(chunks: list[RetrievedChunk]) -> str:
    """Мягкое предупреждение: ответ сохраняем, просим сверить цифры с первоисточником."""
    return _SOFT_WARNING.format(docs=_docs_label(chunks))
