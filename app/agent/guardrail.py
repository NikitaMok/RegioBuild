"""Strict guardrail: цифры/утверждения ответа ⊆ retrieved chunks."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from loguru import logger

from app.vectorstore.types import RetrievedChunk

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?%?")
_YEAR = re.compile(r"^(?:19|20)\d{2}$")
_DATE_DM = re.compile(r"^\d{1,2}\.\d{1,2}$")
_SAFE_REFUSAL = (
    "Внимание: система обнаружила неточность при верификации пунктов. "
    "Чтобы защитить от ошибочных цифр, ответ заблокирован. "
    "Обратитесь к первоисточнику: {docs}."
)


def _numbers_in(text: str) -> set[str]:
    return {m.group(0).replace(",", ".") for m in _NUMBER.finditer(text or "")}


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
    context_parts: list[str] = []
    for chunk in chunks:
        if chunk.section_number:
            context_parts.append(str(chunk.section_number))
        context_parts.append(chunk.text or "")
    context = "\n".join(context_parts)
    context_nums = _numbers_in(context)
    answer_nums = _numbers_in(answer)
    suspicious = {
        n
        for n in answer_nums
        if n not in context_nums
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
    if context and answer:
        SequenceMatcher(None, answer[:2000].lower(), context[:5000].lower()).ratio()
    return True


def build_refusal(chunks: list[RetrievedChunk]) -> str:
    docs = sorted({(c.text.split("]")[0] + "]") if "[" in c.text else "НПА" for c in chunks[:5]})
    label = "; ".join(docs[:3]) if docs else "региональный / федеральный НПА"
    return _SAFE_REFUSAL.format(docs=label)
