"""Управление API-ключами коммерческого контура /api/v1.

Ключ показывается один раз при создании; в БД хранится только SHA-256.

  python -m scripts.manage_api_keys create --name "ООО Клиент" [--daily-limit 200]
  python -m scripts.manage_api_keys list
  python -m scripts.manage_api_keys disable --id <uuid>
"""

from __future__ import annotations

import argparse
import secrets

from sqlalchemy import select

from app.api.auth import hash_api_key
from app.db.models import ApiKey
from app.db.session import get_session

_KEY_PREFIX = "rgb_"


def create_key(client_name: str, daily_limit: int | None) -> int:
    raw_key = _KEY_PREFIX + secrets.token_urlsafe(32)
    record = ApiKey(
        key_hash=hash_api_key(raw_key),
        client_name=client_name,
        daily_limit=daily_limit,
    )
    with get_session() as session:
        session.add(record)
        session.flush()
        key_id = record.id
    print(f"id: {key_id}")
    print(f"client: {client_name}")
    print(f"daily_limit: {daily_limit if daily_limit is not None else 'default'}")
    print(f"api_key (сохраните, повторно не показывается): {raw_key}")
    return 0


def list_keys() -> int:
    with get_session() as session:
        rows = session.execute(
            select(
                ApiKey.id,
                ApiKey.client_name,
                ApiKey.daily_limit,
                ApiKey.is_active,
                ApiKey.created_at,
                ApiKey.last_used_at,
            ).order_by(ApiKey.created_at)
        ).all()
    if not rows:
        print("ключей нет")
        return 0
    for row in rows:
        status = "active" if row.is_active else "disabled"
        print(
            f"{row.id}  {status:8}  {row.client_name:32}  "
            f"limit={row.daily_limit or 'default'}  "
            f"created={row.created_at}  last_used={row.last_used_at or '—'}"
        )
    return 0


def disable_key(key_id: str) -> int:
    with get_session() as session:
        record = session.get(ApiKey, key_id)
        if record is None:
            print(f"ключ {key_id} не найден")
            return 1
        record.is_active = False
    print(f"ключ {key_id} отключён")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--daily-limit", type=int, default=None)

    sub.add_parser("list")

    p_disable = sub.add_parser("disable")
    p_disable.add_argument("--id", required=True)

    args = parser.parse_args()
    if args.command == "create":
        raise SystemExit(create_key(args.name, args.daily_limit))
    if args.command == "list":
        raise SystemExit(list_keys())
    raise SystemExit(disable_key(args.id))


if __name__ == "__main__":
    main()
