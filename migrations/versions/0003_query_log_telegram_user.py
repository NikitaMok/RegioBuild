"""add telegram_user_id to query_logs

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-20

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("query_logs", sa.Column("telegram_user_id", sa.String(length=64), nullable=True))
    op.create_index("ix_query_logs_telegram_user_id", "query_logs", ["telegram_user_id"])


def downgrade() -> None:
    op.drop_index("ix_query_logs_telegram_user_id", table_name="query_logs")
    op.drop_column("query_logs", "telegram_user_id")
