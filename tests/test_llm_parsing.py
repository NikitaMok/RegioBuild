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


def test_parse_json_response_extracts_object_from_preamble() -> None:
    raw = 'Кратко:\n{"name": "автомойка", "value": 3}\nготово.'
    result = parse_json_response(raw, _SampleSchema)
    assert result.name == "автомойка"
    assert result.value == 3


def test_parse_json_response_repairs_trailing_comma() -> None:
    raw = '{"name": "склад", "value": 2,}'
    result = parse_json_response(raw, _SampleSchema)
    assert result.value == 2


def test_parse_json_response_drops_incomplete_items() -> None:
    from app.llm.schemas import ExtractionResult

    raw = (
        '{"region_code": "RU-TA", "business_type": "автосалон", "items": ['
        '{"category": "градостроительные", "description": "Норма парковки.", '
        '"citation": "пункт 5.1", "is_specific": false, "source_level": "региональный"}, '
        '{"category": "градостроительные", "source_level": "федеральный"}'
        "]}"
    )
    result = parse_json_response(raw, ExtractionResult)
    assert len(result.items) == 1
    assert result.items[0].description == "Норма парковки."


def test_friendly_llm_failure_auth() -> None:
    from app.llm.base import LLMProviderError
    from app.llm.errors import friendly_llm_failure

    msg = friendly_llm_failure(
        LLMProviderError("401 oauth: credentials doesn't match db data"),
        mode="info",
    )
    assert "401" in msg
    assert "GIGACHAT_CREDENTIALS" in msg


def test_friendly_llm_failure_parse_is_product_soft() -> None:
    from app.llm.errors import friendly_llm_failure
    from app.llm.parsing import LLMParsingError

    msg = friendly_llm_failure(LLMParsingError("bad json"), mode="info")
    assert "формат" not in msg.lower()
    assert "перечень требований" in msg
    assert "автосалон" in msg
