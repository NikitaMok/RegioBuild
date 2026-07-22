"""Контракт коммерческого API v1: auth по X-API-Key + структурированный ответ."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.api.auth import ApiKeyContext
from app.llm.schemas import (
    ComparisonResult,
    DifferenceItem,
    ExtractionResult,
    RequirementItem,
)

client = TestClient(app)

_VALID_KEY = "rgb_test_key"


@pytest.fixture()
def auth_ok(monkeypatch):
    """Валидный ключ без БД: подменяем lookup и счётчик."""
    import app.api.auth as auth

    monkeypatch.setattr(
        auth,
        "_lookup_active_key",
        lambda key_hash: ("key-id-1", "test-client", None)
        if key_hash == auth.hash_api_key(_VALID_KEY)
        else None,
    )
    monkeypatch.setattr(auth, "_count_key_queries_today", lambda key_id: 0)


def test_v1_info_requires_api_key() -> None:
    response = client.post(
        "/api/v1/info", json={"region": "RU-KDA", "object_type": "автомойка"}
    )
    assert response.status_code == 401


def test_v1_info_rejects_unknown_key(monkeypatch) -> None:
    import app.api.auth as auth

    monkeypatch.setattr(auth, "_lookup_active_key", lambda key_hash: None)
    response = client.post(
        "/api/v1/info",
        json={"region": "RU-KDA", "object_type": "автомойка"},
        headers={"X-API-Key": "rgb_wrong"},
    )
    assert response.status_code == 401


def test_v1_info_enforces_key_daily_limit(monkeypatch, auth_ok) -> None:
    import app.api.auth as auth

    monkeypatch.setattr(auth, "_count_key_queries_today", lambda key_id: 10_000)
    response = client.post(
        "/api/v1/info",
        json={"region": "RU-KDA", "object_type": "автомойка"},
        headers={"X-API-Key": _VALID_KEY},
    )
    assert response.status_code == 429


def test_v1_info_returns_structured_requirements(monkeypatch, auth_ok) -> None:
    import app.agent.graph as agent_graph
    import app.api.routes.v1 as v1_route

    extraction = ExtractionResult(
        region_code="RU-KDA",
        business_type="автомойка",
        items=[
            RequirementItem(
                category="градостроительные",
                description="1 машино-место на 1 бокс.",
                citation="табл.108",
                is_specific=True,
                source_level="региональный",
            ),
            RequirementItem(
                category="санитарные_экологические",
                description="СЗЗ 100 м для моек с 2–5 постами.",
                citation="СанПиН/7.1.3",
                is_specific=True,
                source_level="федеральный",
            ),
        ],
    )
    monkeypatch.setattr(
        agent_graph,
        "run_info_query",
        lambda business_type, region_code: {
            "response_text": "ответ",
            "error": None,
            "extraction": extraction,
            "guardrail_blocked": False,
        },
    )
    monkeypatch.setattr(v1_route, "log_query", lambda **kwargs: "log-1")

    response = client.post(
        "/api/v1/info",
        json={"region": "krasnodar_krai", "object_type": "автомойка"},
        headers={"X-API-Key": _VALID_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["region"] == "RU-KDA"
    assert len(body["requirements"]) == 2

    regional = body["requirements"][0]
    assert regional["citation"]["clause"] == "табл.108"
    assert regional["citation"]["level"] == "regional"
    assert regional["citation"]["region"] == "RU-KDA"
    assert regional["citation"]["last_verified"]

    federal = body["requirements"][1]
    assert federal["citation"]["level"] == "federal"
    assert federal["citation"]["region"] == "RU-FED"
    assert "СанПиН" in federal["citation"]["document"]

    source_regions = {s["region"] for s in body["sources"]}
    assert source_regions == {"RU-KDA", "RU-FED"}


def test_v1_info_blocked_response_has_no_structured_payload(monkeypatch, auth_ok) -> None:
    import app.agent.graph as agent_graph
    import app.api.routes.v1 as v1_route

    extraction = ExtractionResult(region_code="RU-KDA", business_type="автомойка", items=[])
    monkeypatch.setattr(
        agent_graph,
        "run_info_query",
        lambda business_type, region_code: {
            "response_text": "отказ",
            "error": None,
            "extraction": extraction,
            "guardrail_blocked": True,
        },
    )
    monkeypatch.setattr(v1_route, "log_query", lambda **kwargs: "log-2")

    response = client.post(
        "/api/v1/info",
        json={"region": "RU-KDA", "object_type": "автомойка"},
        headers={"X-API-Key": _VALID_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["guardrail_blocked"] is True
    assert body["requirements"] == []
    assert body["sources"] == []


def test_v1_compare_returns_differences_and_sources(monkeypatch, auth_ok) -> None:
    import app.agent.graph as agent_graph
    import app.api.routes.v1 as v1_route

    comparison = ComparisonResult(
        region_a="RU-MOS",
        region_b="RU-SVE",
        business_type="склад",
        overall_summary="Требования различаются по парковке.",
        common_requirements=[],
        differences=[
            DifferenceItem(
                category="градостроительные",
                region_a_value="6–8 машино-мест на работающих",
                region_b_value="региональные требования отсутствуют",
                summary="В Московской области парковка нормируется приложением 10.",
                citation_a="прил.10",
                citation_b="",
                is_specific=True,
                source_level="региональный",
            )
        ],
    )
    monkeypatch.setattr(
        agent_graph,
        "run_compare_query",
        lambda business_type, region_a, region_b: {
            "response_text": "сравнение",
            "error": None,
            "comparison": comparison,
            "guardrail_blocked": False,
        },
    )
    monkeypatch.setattr(v1_route, "log_query", lambda **kwargs: "log-3")

    response = client.post(
        "/api/v1/compare",
        json={"region_a": "RU-MOS", "region_b": "RU-SVE", "object_type": "склад"},
        headers={"X-API-Key": _VALID_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == "Требования различаются по парковке."
    assert len(body["differences"]) == 1

    diff = body["differences"][0]
    assert diff["region_a"]["region"] == "RU-MOS"
    assert diff["region_a"]["citation"]["clause"] == "прил.10"
    assert diff["region_b"]["citation"] is None

    source_regions = {s["region"] for s in body["sources"]}
    assert source_regions == {"RU-MOS", "RU-SVE", "RU-FED"}


def test_v1_auth_disabled_allows_requests(monkeypatch) -> None:
    import app.agent.graph as agent_graph
    import app.api.routes.v1 as v1_route
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "api_auth_enabled", False)
    monkeypatch.setattr(
        agent_graph,
        "run_info_query",
        lambda business_type, region_code: {"response_text": "ок", "error": None},
    )
    monkeypatch.setattr(v1_route, "log_query", lambda **kwargs: None)

    response = client.post(
        "/api/v1/info", json={"region": "RU-KDA", "object_type": "автомойка"}
    )
    assert response.status_code == 200


def test_api_key_context_dataclass() -> None:
    ctx = ApiKeyContext(id="abc", client_name="client")
    assert ctx.id == "abc"
