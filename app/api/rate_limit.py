from __future__ import annotations

import datetime as dt

from loguru import logger
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import QueryLog
from app.db.session import get_session


class RateLimitExceeded(Exception):
    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"дневной лимит запросов исчерпан ({limit})")


def count_user_queries_today(telegram_user_id: str) -> int:
    day_start = dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with get_session() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(QueryLog)
                .where(
                    QueryLog.telegram_user_id == telegram_user_id,
                    QueryLog.created_at >= day_start,
                )
            )
            or 0
        )


def ensure_within_daily_limit(telegram_user_id: str | None) -> None:
    """Без user_id лимит не проверяем. Ошибка БД не должна ронять запрос."""
    if not telegram_user_id:
        return
    limit = get_settings().daily_query_limit
    try:
        used = count_user_queries_today(telegram_user_id)
    except Exception as exc:
        logger.warning(f"не удалось проверить лимит запросов: {exc}")
        return
    if used >= limit:
        raise RateLimitExceeded(limit)
