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


def parse_json_response(raw_text: str, schema: type[ModelT]) -> ModelT:
    """Модели любят оборачивать JSON в ```json ... ``` — убираем обёртку и валидируем."""
    cleaned = _strip_code_fence(raw_text)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMParsingError(f"ответ модели не JSON: {exc}\n{raw_text[:500]}") from exc

    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise LLMParsingError(f"ответ модели не соответствует схеме: {exc}\n{raw_text[:500]}") from exc
