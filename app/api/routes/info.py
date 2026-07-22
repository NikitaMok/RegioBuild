from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from app.agent.nodes import audit_sections_from_state
from app.api.query_logging import log_query
from app.api.rate_limit import RateLimitExceeded, ensure_within_daily_limit
from app.api.schemas import AgentResponse, InfoRequest
from app.core.business_type import MAX_QUERY_LENGTH, looks_like_prompt_injection
from app.core.regions import REGIONS, resolve_region_code

router = APIRouter(tags=["info"])


@router.post("/info", response_model=AgentResponse)
def get_business_requirements(payload: InfoRequest, request: Request) -> AgentResponse:
    try:
        region_code = resolve_region_code(payload.region_code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if region_code not in REGIONS:
        raise HTTPException(status_code=422, detail=f"неизвестный регион: {payload.region_code}")
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
        from app.agent.graph import run_info_query

        agent_state = run_info_query(payload.business_type, region_code)
    except Exception as exc:
        logger.exception("агент упал с необработанным исключением")
        raise HTTPException(status_code=500, detail=f"внутренняя ошибка агента: {exc}") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    response_text = agent_state.get("response_text", "")
    error = agent_state.get("error")

    query_log_id = log_query(
        mode="info",
        region_a=region_code,
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
