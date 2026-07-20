from __future__ import annotations

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.api.query_logging import log_query
from app.api.rate_limit import RateLimitExceeded, ensure_within_daily_limit
from app.api.schemas import AgentResponse, CompareRequest
from app.core.regions import REGIONS

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=AgentResponse)
def compare_regions(payload: CompareRequest) -> AgentResponse:
    for region_code in (payload.region_a, payload.region_b):
        if region_code not in REGIONS:
            raise HTTPException(status_code=422, detail=f"неизвестный регион: {region_code}")

    if payload.region_a == payload.region_b:
        raise HTTPException(status_code=422, detail="для сравнения нужны два разных региона")

    try:
        ensure_within_daily_limit(payload.telegram_user_id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Дневной лимит запросов исчерпан ({exc.limit}). Попробуйте завтра.",
        ) from exc

    try:
        from app.agent.graph import run_compare_query

        agent_state = run_compare_query(payload.business_type, payload.region_a, payload.region_b)
    except Exception as exc:
        logger.exception("агент упал с необработанным исключением")
        raise HTTPException(status_code=500, detail=f"внутренняя ошибка агента: {exc}") from exc

    response_text = agent_state.get("response_text", "")

    query_log_id = log_query(
        mode="compare",
        region_a=payload.region_a,
        region_b=payload.region_b,
        business_type=payload.business_type,
        response_text=response_text,
        telegram_user_id=payload.telegram_user_id,
    )

    return AgentResponse(
        response_text=response_text,
        error=agent_state.get("error"),
        query_log_id=query_log_id,
    )
