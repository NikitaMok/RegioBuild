"""Alembic revision: audit fields on query_logs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_query_log_audit"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("query_logs") as batch:
        batch.add_column(sa.Column("client_ip", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("user_agent", sa.String(length=256), nullable=True))
        batch.add_column(sa.Column("error_text", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("query_logs") as batch:
        batch.drop_column("error_text")
        batch.drop_column("user_agent")
        batch.drop_column("client_ip")
