"""E2E-сценарии через API (агент замокан) — структура ответа под QA."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)

QA_CASES = [
    {"business_type": "автомойка", "region_code": "krasnodar_krai"},
    {"business_type": "офис", "region_code": "sverdlovsk_oblast"},
]


def test_e2e_info_scenarios_have_legal_phrasing(monkeypatch) -> None:
    import app.agent.graph as agent_graph
    import app.api.routes.info as info_route

    def _fake_info(business_type: str, region_code: str) -> dict:
        return {
            "response_text": (
                f"Правовое регулирование: акт ({region_code})\n"
                f"Федеральные нормы (применяются при отсутствии региональных): СП\n"
                f"Требования для «{business_type}»\n"
                "Что требуется проверить дополнительно\n"
                "⚠️ Ответ носит справочный характер и не является юридической консультацией."
            ),
            "error": None,
        }

    monkeypatch.setattr(agent_graph, "run_info_query", _fake_info)
    monkeypatch.setattr(info_route, "log_query", lambda **kwargs: "e2e-1")
    monkeypatch.setattr(info_route, "ensure_within_daily_limit", lambda _uid: None)

    for case in QA_CASES:
        response = client.post("/info", json=case)
        assert response.status_code == 200
        text = response.json()["response_text"]
        assert "Правовое регулирование" in text
        assert "Федеральные нормы" in text
        assert "юридической консультацией" in text


def test_e2e_compare_scenario(monkeypatch) -> None:
    import app.agent.graph as agent_graph
    import app.api.routes.compare as compare_route

    monkeypatch.setattr(
        agent_graph,
        "run_compare_query",
        lambda *args, **kwargs: {
            "response_text": "Чем отличаются\n1. Срок\nЧто совпадает\nЧто требуется проверить дополнительно",
            "error": None,
        },
    )
    monkeypatch.setattr(compare_route, "log_query", lambda **kwargs: "e2e-2")
    monkeypatch.setattr(compare_route, "ensure_within_daily_limit", lambda _uid: None)

    response = client.post(
        "/compare",
        json={
            "business_type": "автосервис",
            "region_a": "moscow_oblast",
            "region_b": "krasnodar_krai",
        },
    )
    assert response.status_code == 200
    text = response.json()["response_text"]
    assert text.index("Чем отличаются") < text.index("Что совпадает")
