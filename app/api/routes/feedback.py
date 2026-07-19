from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.query_logging import save_feedback
from app.api.schemas import FeedbackRequest

router = APIRouter(tags=["feedback"])


@router.post("/feedback")
def submit_feedback(payload: FeedbackRequest) -> dict:
    found = save_feedback(payload.query_log_id, payload.vote)
    if not found:
        raise HTTPException(status_code=404, detail="запрос с таким query_log_id не найден")
    return {"status": "ok"}
