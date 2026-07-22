"""API v1 — коммерческий контур (Telegram остаётся воронкой)."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request
from loguru import logger
from prometheus_client import Counter

from app.agent.nodes import audit_sections_from_state
from app.api.query_logging import log_query
from app.api.rate_limit import RateLimitExceeded, ensure_within_daily_limit
from app.api.schemas_v1 import AgentV1Response, CompareV1Request, InfoV1Request
from app.core.business_type import MAX_QUERY_LENGTH, looks_like_prompt_injection
from app.core.regions import REGIONS, resolve_region_code

router = APIRouter(prefix="/api/v1", tags=["v1"])

GUARDRAIL_BLOCKS = Counter(
    "regiobuild_guardrail_blocks_total",
    "Ответы, заблокированные Strict Guardrail",
    ["mode"],
)


@router.post("/info", response_model=AgentV1Response)
def info_v1(payload: InfoV1Request, request: Request) -> AgentV1Response:
    try:
        region = resolve_region_code(payload.region)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if region not in REGIONS:
        raise HTTPException(status_code=422, detail=f"неизвестный регион: {payload.region}")
    if len(payload.object_type) > MAX_QUERY_LENGTH:
        raise HTTPException(status_code=422, detail="слишком длинный тип объекта")
    if looks_like_prompt_injection(payload.object_type):
        raise HTTPException(status_code=422, detail="запрос отклонён политикой безопасности")

    try:
        ensure_within_daily_limit(payload.telegram_user_id)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    started = time.perf_counter()
    try:
        from app.agent.graph import run_info_query

        state = run_info_query(payload.object_type, region)
    except Exception as exc:
        logger.exception("v1/info agent failure")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    blocked = bool(state.get("guardrail_blocked"))
    if blocked:
        GUARDRAIL_BLOCKS.labels(mode="info").inc()

    latency_ms = int((time.perf_counter() - started) * 1000)
    response_text = state.get("response_text", "")
    error = state.get("error")
    query_log_id = log_query(
        mode="info",
        region_a=region,
        business_type=payload.object_type,
        response_text=response_text,
        telegram_user_id=payload.telegram_user_id,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        error_text=error,
        retrieved_sections=audit_sections_from_state(state),
        latency_ms=latency_ms,
    )
    return AgentV1Response(
        response_text=response_text,
        error=error,
        query_log_id=query_log_id,
        guardrail_blocked=blocked,
        region=region,
        object_type=payload.object_type,
    )


@router.post("/compare", response_model=AgentV1Response)
def compare_v1(payload: CompareV1Request, request: Request) -> AgentV1Response:
    try:
        region_a = resolve_region_code(payload.region_a)
        region_b = resolve_region_code(payload.region_b)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if region_a not in REGIONS or region_b not in REGIONS:
        raise HTTPException(status_code=422, detail="неизвестный регион")
    if region_a == region_b:
        raise HTTPException(status_code=422, detail="нужны два разных региона")
    if len(payload.object_type) > MAX_QUERY_LENGTH:
        raise HTTPException(status_code=422, detail="слишком длинный тип объекта")
    if looks_like_prompt_injection(payload.object_type):
        raise HTTPException(status_code=422, detail="запрос отклонён политикой безопасности")

    try:
        ensure_within_daily_limit(payload.telegram_user_id)
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    # parameter пока влияет на transformed_query через префикс object_type
    object_type = payload.object_type
    if payload.parameter:
        object_type = f"{payload.object_type} {payload.parameter}"

    started = time.perf_counter()
    try:
        from app.agent.graph import run_compare_query

        state = run_compare_query(object_type, region_a, region_b)
    except Exception as exc:
        logger.exception("v1/compare agent failure")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    blocked = bool(state.get("guardrail_blocked"))
    if blocked:
        GUARDRAIL_BLOCKS.labels(mode="compare").inc()

    latency_ms = int((time.perf_counter() - started) * 1000)
    response_text = state.get("response_text", "")
    error = state.get("error")
    query_log_id = log_query(
        mode="compare",
        region_a=region_a,
        region_b=region_b,
        business_type=payload.object_type,
        response_text=response_text,
        telegram_user_id=payload.telegram_user_id,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        error_text=error,
        retrieved_sections=audit_sections_from_state(state),
        latency_ms=latency_ms,
    )
    return AgentV1Response(
        response_text=response_text,
        error=error,
        query_log_id=query_log_id,
        guardrail_blocked=blocked,
        region=f"{region_a}|{region_b}",
        object_type=payload.object_type,
    )
