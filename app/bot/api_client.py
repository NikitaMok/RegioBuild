"""Клиент бота к backend (Bot -> API -> Agent, см. схему в README)."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings


class ApiClientError(RuntimeError):
    pass


@dataclass
class AgentAnswer:
    response_text: str
    query_log_id: str | None


async def _post(path: str, payload: dict) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.api_base_url, timeout=60) as client:
        try:
            response = await client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiClientError(f"backend недоступен или вернул ошибку: {exc}") from exc
    return response.json()


async def request_info(business_type: str, region_code: str) -> AgentAnswer:
    data = await _post("/info", {"business_type": business_type, "region_code": region_code})
    return AgentAnswer(response_text=data["response_text"], query_log_id=data.get("query_log_id"))


async def request_compare(business_type: str, region_a: str, region_b: str) -> AgentAnswer:
    data = await _post(
        "/compare",
        {"business_type": business_type, "region_a": region_a, "region_b": region_b},
    )
    return AgentAnswer(response_text=data["response_text"], query_log_id=data.get("query_log_id"))


async def send_feedback(query_log_id: str, vote: str) -> None:
    try:
        await _post("/feedback", {"query_log_id": query_log_id, "vote": vote})
    except ApiClientError:
        # фидбек — вспомогательная штука, если backend не принял его,
        # не хотим ломать пользователю остальной диалог с ботом
        pass
