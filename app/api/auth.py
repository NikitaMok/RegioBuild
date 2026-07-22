"""Аутентификация коммерческого контура /api/v1 по X-API-Key.

Ключ выдаётся клиенту один раз (scripts.manage_api_keys), в БД — только SHA-256.
Legacy-эндпоинты /info и /compare (Telegram-бот) ключом не защищаются.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass

from fastapi import HTTPException, Request
from loguru import logger
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import ApiKey, QueryLog
from app.db.session import get_session

API_KEY_HEADER = "X-API-Key"


@dataclass(frozen=True)
class ApiKeyContext:
    id: str
    client_name: str


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _lookup_active_key(key_hash: str) -> tuple[str, str, int | None] | None:
    """(id, client_name, daily_limit) или None."""
    with get_session() as session:
        row = session.execute(
            select(ApiKey.id, ApiKey.client_name, ApiKey.daily_limit).where(
                ApiKey.key_hash == key_hash,
                ApiKey.is_active.is_(True),
            )
        ).first()
        if row is None:
            return None
        session.execute(
            ApiKey.__table__.update()
            .where(ApiKey.id == row.id)
            .values(last_used_at=dt.datetime.now(dt.timezone.utc))
        )
        return (row.id, row.client_name, row.daily_limit)


def _count_key_queries_today(api_key_id: str) -> int:
    day_start = dt.datetime.now(dt.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    with get_session() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(QueryLog)
                .where(
                    QueryLog.api_key_id == api_key_id,
                    QueryLog.created_at >= day_start,
                )
            )
            or 0
        )


def require_api_key(request: Request) -> ApiKeyContext | None:
    """FastAPI dependency: валидный активный ключ + дневной лимит по ключу.

    API_AUTH_ENABLED=false отключает проверку (локальная разработка/тесты).
    """
    settings = get_settings()
    if not settings.api_auth_enabled:
        return None

    raw_key = (request.headers.get(API_KEY_HEADER) or "").strip()
    if not raw_key:
        raise HTTPException(
            status_code=401,
            detail=f"нужен заголовок {API_KEY_HEADER}; ключ выдаёт владелец сервиса",
        )

    try:
        found = _lookup_active_key(hash_api_key(raw_key))
    except Exception as exc:
        logger.error(f"проверка API-ключа недоступна: {exc}")
        raise HTTPException(status_code=503, detail="сервис авторизации временно недоступен") from exc

    if found is None:
        raise HTTPException(status_code=401, detail="неизвестный или отключённый API-ключ")

    key_id, client_name, daily_limit = found
    limit = daily_limit if daily_limit is not None else settings.daily_query_limit
    try:
        used = _count_key_queries_today(key_id)
    except Exception as exc:
        logger.warning(f"не удалось посчитать запросы по ключу {client_name}: {exc}")
        used = 0
    if used >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"дневной лимит запросов по ключу исчерпан ({limit})",
        )
    return ApiKeyContext(id=key_id, client_name=client_name)
