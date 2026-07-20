from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app
from app.core.regions import REGIONS

# только HTTP-контракт; качество агента — в app/eval/
client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_regions_returns_all_known_regions() -> None:
    response = client.get("/regions")
    assert response.status_code == 200
    codes = {region["code"] for region in response.json()["regions"]}
    assert codes == set(REGIONS.keys())


def test_info_rejects_unknown_region() -> None:
    response = client.post("/info", json={"business_type": "кафе", "region_code": "narnia"})
    assert response.status_code == 422


def test_info_returns_agent_answer_with_query_log_id(monkeypatch) -> None:
    import app.agent.graph as agent_graph
    import app.api.routes.info as info_route

    monkeypatch.setattr(
        agent_graph,
        "run_info_query",
        lambda business_type, region_code: {"response_text": "готовый ответ", "error": None},
    )
    monkeypatch.setattr(info_route, "log_query", lambda **kwargs: "log-id-123")

    response = client.post("/info", json={"business_type": "кафе", "region_code": "moscow_oblast"})

    assert response.status_code == 200
    body = response.json()
    assert body["response_text"] == "готовый ответ"
    assert body["query_log_id"] == "log-id-123"


def test_info_returns_500_when_agent_raises(monkeypatch) -> None:
    import app.agent.graph as agent_graph

    def _raise(*args, **kwargs):
        raise RuntimeError("векторный индекс недоступен")

    monkeypatch.setattr(agent_graph, "run_info_query", _raise)

    response = client.post("/info", json={"business_type": "кафе", "region_code": "moscow_oblast"})
    assert response.status_code == 500


def test_compare_rejects_identical_regions() -> None:
    response = client.post(
        "/compare",
        json={"business_type": "кафе", "region_a": "moscow_oblast", "region_b": "moscow_oblast"},
    )
    assert response.status_code == 422


def test_compare_rejects_unknown_region() -> None:
    response = client.post(
        "/compare",
        json={"business_type": "кафе", "region_a": "moscow_oblast", "region_b": "narnia"},
    )
    assert response.status_code == 422


def test_compare_returns_agent_answer(monkeypatch) -> None:
    import app.agent.graph as agent_graph
    import app.api.routes.compare as compare_route

    monkeypatch.setattr(
        agent_graph,
        "run_compare_query",
        lambda business_type, region_a, region_b: {"response_text": "сравнение готово", "error": None},
    )
    monkeypatch.setattr(compare_route, "log_query", lambda **kwargs: "log-id-456")

    response = client.post(
        "/compare",
        json={"business_type": "кафе", "region_a": "moscow_oblast", "region_b": "krasnodar_krai"},
    )

    assert response.status_code == 200
    assert response.json()["response_text"] == "сравнение готово"


def test_feedback_for_missing_query_log_returns_404(monkeypatch) -> None:
    import app.api.routes.feedback as feedback_route

    monkeypatch.setattr(feedback_route, "save_feedback", lambda query_log_id, vote: False)

    response = client.post("/feedback", json={"query_log_id": "missing-id", "vote": "up"})
    assert response.status_code == 404


def test_info_returns_429_when_daily_limit_exceeded(monkeypatch) -> None:
    import app.api.routes.info as info_route
    from app.api.rate_limit import RateLimitExceeded

    def _raise_limit(telegram_user_id: str | None) -> None:
        raise RateLimitExceeded(30)

    monkeypatch.setattr(info_route, "ensure_within_daily_limit", _raise_limit)

    response = client.post(
        "/info",
        json={"business_type": "кафе", "region_code": "moscow_oblast", "telegram_user_id": "42"},
    )
    assert response.status_code == 429
    assert "лимит" in response.json()["detail"].lower()
