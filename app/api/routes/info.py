from __future__ import annotations

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.agent.graph import run_info_query
from app.api.query_logging import log_query
from app.api.schemas import AgentResponse, InfoRequest
from app.core.regions import REGIONS

router = APIRouter(tags=["info"])


@router.post("/info", response_model=AgentResponse)
def get_business_requirements(payload: InfoRequest) -> AgentResponse:
    if payload.region_code not in REGIONS:
        raise HTTPException(status_code=422, detail=f"неизвестный регион: {payload.region_code}")

    try:
        agent_state = run_info_query(payload.business_type, payload.region_code)
    except Exception as exc:
        logger.exception("агент упал с необработанным исключением")
        raise HTTPException(status_code=500, detail=f"внутренняя ошибка агента: {exc}") from exc

    response_text = agent_state.get("response_text", "")

    query_log_id = log_query(
        mode="info",
        region_a=payload.region_code,
        business_type=payload.business_type,
        response_text=response_text,
    )

    return AgentResponse(
        response_text=response_text,
        error=agent_state.get("error"),
        query_log_id=query_log_id,
    )
