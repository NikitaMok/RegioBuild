"""Alembic revision: retrieval audit fields on query_logs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_query_log_retrieval_audit"
down_revision = "0004_query_log_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("query_logs") as batch:
        batch.add_column(sa.Column("retrieved_sections", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("query_logs") as batch:
        batch.drop_column("latency_ms")
        batch.drop_column("retrieved_sections")
