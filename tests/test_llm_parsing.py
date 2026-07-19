from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.llm.parsing import LLMParsingError, parse_json_response


class _SampleSchema(BaseModel):
    name: str
    value: int


def test_parse_json_response_accepts_plain_json() -> None:
    result = parse_json_response('{"name": "склад", "value": 5}', _SampleSchema)
    assert result.name == "склад"
    assert result.value == 5


def test_parse_json_response_strips_markdown_code_fence() -> None:
    raw = 'Вот результат:\n```json\n{"name": "кафе", "value": 1}\n```'
    result = parse_json_response(raw, _SampleSchema)
    assert result.name == "кафе"
    assert result.value == 1


def test_parse_json_response_invalid_json_raises() -> None:
    with pytest.raises(LLMParsingError):
        parse_json_response("это не JSON, а обычный текст", _SampleSchema)


def test_parse_json_response_schema_mismatch_raises() -> None:
    with pytest.raises(LLMParsingError):
        parse_json_response('{"name": "склад"}', _SampleSchema)  # value отсутствует
