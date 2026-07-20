"""HTTP-клиент бота к FastAPI."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import get_settings


class ApiClientError(RuntimeError):
    pass


class ApiRateLimitError(ApiClientError):
    pass


@dataclass
class AgentAnswer:
    response_text: str
    query_log_id: str | None


async def _post(path: str, payload: dict) -> dict:
    settings = get_settings()
    async with httpx.AsyncClient(base_url=settings.api_base_url, timeout=180) as client:
        try:
            response = await client.post(path, json=payload)
            if response.status_code == 429:
                detail = "Дневной лимит запросов исчерпан. Попробуйте завтра."
                try:
                    body = response.json()
                    if isinstance(body.get("detail"), str):
                        detail = body["detail"]
                except Exception:
                    pass
                raise ApiRateLimitError(detail)
            response.raise_for_status()
        except ApiRateLimitError:
            raise
        except httpx.HTTPError as exc:
            raise ApiClientError(f"backend недоступен или вернул ошибку: {exc}") from exc
    return response.json()


async def request_info(
    business_type: str,
    region_code: str,
    telegram_user_id: str | None = None,
) -> AgentAnswer:
    payload = {"business_type": business_type, "region_code": region_code}
    if telegram_user_id:
        payload["telegram_user_id"] = telegram_user_id
    data = await _post("/info", payload)
    return AgentAnswer(response_text=data["response_text"], query_log_id=data.get("query_log_id"))


async def request_compare(
    business_type: str,
    region_a: str,
    region_b: str,
    telegram_user_id: str | None = None,
) -> AgentAnswer:
    payload = {"business_type": business_type, "region_a": region_a, "region_b": region_b}
    if telegram_user_id:
        payload["telegram_user_id"] = telegram_user_id
    data = await _post("/compare", payload)
    return AgentAnswer(response_text=data["response_text"], query_log_id=data.get("query_log_id"))


async def send_feedback(query_log_id: str, vote: str) -> None:
    try:
        await _post("/feedback", {"query_log_id": query_log_id, "vote": vote})
    except ApiClientError:
        pass
