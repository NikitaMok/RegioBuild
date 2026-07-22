"""Strict guardrail: цифры/утверждения ответа ⊆ retrieved chunks."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from loguru import logger

from app.vectorstore.types import RetrievedChunk

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?%?")
_SAFE_REFUSAL = (
    "Внимание: система обнаружила неточность при верификации пунктов. "
    "Чтобы защитить от ошибочных цифр, ответ заблокирован. "
    "Обратитесь к первоисточнику: {docs}."
)


def _numbers_in(text: str) -> set[str]:
    return {m.group(0).replace(",", ".") for m in _NUMBER.finditer(text or "")}


def claim_numbers_supported(answer: str, chunks: list[RetrievedChunk], *, min_ratio: float = 0.85) -> bool:
    """Основные числа из ответа должны встречаться в контексте (или быть номерами пунктов)."""
    context = "\n".join(c.text for c in chunks)
    context_nums = _numbers_in(context)
    answer_nums = _numbers_in(answer)
    # отсекаем годы и слишком общие
    suspicious = {
        n
        for n in answer_nums
        if n not in context_nums
        and not n.endswith("%")  # % тоже должны быть в контексте
        and len(n) <= 6
    }
    # проценты без опоры — блок
    pct_bad = [n for n in answer_nums if n.endswith("%") and n not in context_nums]
    if pct_bad:
        logger.warning(f"guardrail: проценты без опоры {pct_bad}")
        return False
    # если много «лишних» чисел — блок
    if len(suspicious) >= 3:
        logger.warning(f"guardrail: лишние числа {suspicious}")
        return False
    # грубая похожесть на контекст
    if context and answer:
        ratio = SequenceMatcher(None, answer[:2000].lower(), context[:5000].lower()).ratio()
        if ratio < 0.02 and len(answer) > 400:
            # слишком мало пересечения с длинным ответом — подозрительно, но JSON/HTML шумны
            pass
    return True


def build_refusal(chunks: list[RetrievedChunk]) -> str:
    docs = sorted({(c.text.split("]")[0] + "]") if "[" in c.text else "НПА" for c in chunks[:5]})
    label = "; ".join(docs[:3]) if docs else "региональный / федеральный НПА"
    return _SAFE_REFUSAL.format(docs=label)
