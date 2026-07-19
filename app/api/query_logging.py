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
            return True
    except Exception as exc:
        logger.warning(f"не удалось сохранить фидбек для {query_log_id}: {exc}")
        return False
