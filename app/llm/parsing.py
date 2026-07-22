from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)

JSON_CODE_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


class LLMParsingError(RuntimeError):
    pass


def _strip_code_fence(text: str) -> str:
    match = JSON_CODE_FENCE.search(text)
    return match.group(1) if match else text.strip()


def _extract_balanced_object(text: str) -> str | None:
    """Вырезает первый полный JSON-объект `{...}` с учётом строк и экранирования."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def _repair_common_json_glitches(text: str) -> str:
    # хвостовые запятые перед } или ]
    repaired = re.sub(r",\s*([}\]])", r"\1", text)
    return repaired


def _candidate_payloads(raw_text: str) -> list[str]:
    cleaned = _strip_code_fence(raw_text)
    candidates: list[str] = [cleaned]
    balanced = _extract_balanced_object(cleaned)
    if balanced and balanced not in candidates:
        candidates.append(balanced)
    # если fence не сработал — пробуем весь сырой текст
    if cleaned != raw_text.strip():
        balanced_raw = _extract_balanced_object(raw_text)
        if balanced_raw and balanced_raw not in candidates:
            candidates.append(balanced_raw)
    expanded: list[str] = []
    for item in candidates:
        expanded.append(item)
        repaired = _repair_common_json_glitches(item)
        if repaired != item:
            expanded.append(repaired)
    return expanded


def parse_json_response(raw_text: str, schema: type[ModelT]) -> ModelT:
    """Парсит JSON из ответа модели (fence, преамбула, мелкие глюки GigaChat)."""
    if not (raw_text or "").strip():
        raise LLMParsingError("пустой ответ модели")

    last_json_error: Exception | None = None
    for candidate in _candidate_payloads(raw_text):
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_json_error = exc
            continue
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise LLMParsingError(
                f"ответ модели не соответствует схеме: {exc}\n{raw_text[:500]}"
            ) from exc

    detail = f"{last_json_error}" if last_json_error else "не найден JSON-объект"
    raise LLMParsingError(f"ответ модели не JSON: {detail}\n{raw_text[:500]}")
