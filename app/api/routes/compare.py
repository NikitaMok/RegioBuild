from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from app.agent.nodes import audit_sections_from_state
from app.api.query_logging import log_query
from app.api.rate_limit import RateLimitExceeded, ensure_within_daily_limit
from app.api.schemas import AgentResponse, CompareRequest
from app.core.business_type import MAX_QUERY_LENGTH, looks_like_prompt_injection
from app.core.regions import REGIONS

router = APIRouter(tags=["compare"])


@router.post("/compare", response_model=AgentResponse)
def compare_regions(payload: CompareRequest, request: Request) -> AgentResponse:
    for region_code in (payload.region_a, payload.region_b):
        if region_code not in REGIONS:
            raise HTTPException(status_code=422, detail=f"неизвестный регион: {region_code}")

    if payload.region_a == payload.region_b:
        raise HTTPException(status_code=422, detail="для сравнения нужны два разных региона")
    if len(payload.business_type) > MAX_QUERY_LENGTH:
        raise HTTPException(status_code=422, detail="слишком длинный тип бизнеса")
    if looks_like_prompt_injection(payload.business_type):
        raise HTTPException(status_code=422, detail="запрос отклонён политикой безопасности")

    try:
        ensure_within_daily_limit(payload.telegram_user_id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=f"Дневной лимит запросов исчерпан ({exc.limit}). Попробуйте завтра.",
        ) from exc

    started = time.perf_counter()
    try:
        from app.agent.graph import run_compare_query

        agent_state = run_compare_query(payload.business_type, payload.region_a, payload.region_b)
    except Exception as exc:
        logger.exception("агент упал с необработанным исключением")
        raise HTTPException(status_code=500, detail=f"внутренняя ошибка агента: {exc}") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    response_text = agent_state.get("response_text", "")
    error = agent_state.get("error")

    query_log_id = log_query(
        mode="compare",
        region_a=payload.region_a,
        region_b=payload.region_b,
        business_type=payload.business_type,
        response_text=response_text,
        telegram_user_id=payload.telegram_user_id,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        error_text=error,
        retrieved_sections=audit_sections_from_state(agent_state),
        latency_ms=latency_ms,
    )

    return AgentResponse(
        response_text=response_text,
        error=error,
        query_log_id=query_log_id,
    )
