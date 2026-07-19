"""add feedback column to query_logs

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("query_logs", sa.Column("feedback", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("query_logs", "feedback")
