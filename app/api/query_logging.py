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
    """Пишем историю запросов для аналитики и подбора кейсов в eval-датасет.

    Возвращаем id записи, чтобы бот мог позже привязать к ней фидбек
    пользователя (👍/👎). Если БД недоступна — это не должно ронять ответ
    пользователю, поэтому ошибку только логируем и возвращаем None.
    """
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
    """Отмечаем, помог ли ответ пользователю. Возвращает False, если записи
    с таким id не нашлось (например, лог не сохранился с первого раза)."""
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
