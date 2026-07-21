from __future__ import annotations

from fastapi import APIRouter, HTTPException
from loguru import logger

from app.api.query_logging import feedback_counts, save_feedback
from app.api.schemas import FeedbackRequest

router = APIRouter(tags=["feedback"])


@router.post("/feedback")
def submit_feedback(payload: FeedbackRequest) -> dict:
    found = save_feedback(payload.query_log_id, payload.vote)
    if not found:
        raise HTTPException(status_code=404, detail="запрос с таким query_log_id не найден")
    counts = feedback_counts()
    logger.info(f"feedback totals up={counts['up']} down={counts['down']} total={counts['total']}")
    return {"status": "ok", "totals": counts}
