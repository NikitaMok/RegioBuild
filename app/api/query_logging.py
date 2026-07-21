from __future__ import annotations

from loguru import logger

from app.db.models import QueryLog
from app.db.session import get_session


def log_query(
    mode: str,
    region_a: str,
    business_type: str,
    response_text: str,
    region_b: str | None = None,
    telegram_user_id: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    error_text: str | None = None,
    retrieved_sections: list[dict] | None = None,
    latency_ms: int | None = None,
) -> str | None:
    """Пишет запрос в query_logs. При ошибке БД — None, ответ пользователю не роняем."""
    try:
        with get_session() as session:
            query_log = QueryLog(
                mode=mode,
                region_a=region_a,
                region_b=region_b,
                business_type=business_type,
                answer=response_text,
                telegram_user_id=telegram_user_id,
                client_ip=client_ip,
                user_agent=(user_agent or "")[:256] or None,
                error_text=error_text,
                retrieved_sections=retrieved_sections,
                latency_ms=latency_ms,
            )
            session.add(query_log)
            session.flush()
            return query_log.id
    except Exception as exc:
        logger.warning(f"не удалось записать QueryLog: {exc}")
        return None


def save_feedback(query_log_id: str, vote: str) -> bool:
    """Сохраняет 👍/👎. False, если записи с таким id нет."""
    try:
        with get_session() as session:
            query_log = session.get(QueryLog, query_log_id)
            if query_log is None:
                return False
            query_log.feedback = vote
            logger.info(
                f"feedback recorded vote={vote} query_log_id={query_log_id} "
                f"mode={query_log.mode} region_a={query_log.region_a}"
            )
            return True
    except Exception as exc:
        logger.warning(f"не удалось сохранить фидбек для {query_log_id}: {exc}")
        return False


def feedback_counts() -> dict[str, int]:
    """Счётчики 👍/👎 для мониторинга качества."""
    try:
        from sqlalchemy import select

        with get_session() as session:
            votes = session.scalars(
                select(QueryLog.feedback).where(QueryLog.feedback.isnot(None))
            ).all()
        up = sum(1 for vote in votes if vote == "up")
        down = sum(1 for vote in votes if vote == "down")
        return {"up": up, "down": down, "total": up + down}
    except Exception as exc:
        logger.warning(f"не удалось посчитать feedback: {exc}")
        return {"up": 0, "down": 0, "total": 0}
