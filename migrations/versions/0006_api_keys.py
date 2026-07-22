"""Alembic revision: api_keys table + api_key_id on query_logs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_api_keys"
down_revision = "0005_query_log_retrieval_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("client_name", sa.String(length=128), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)
    with op.batch_alter_table("query_logs") as batch:
        batch.add_column(sa.Column("api_key_id", sa.String(length=36), nullable=True))
        batch.create_index("ix_query_logs_api_key_id", ["api_key_id"])


def downgrade() -> None:
    with op.batch_alter_table("query_logs") as batch:
        batch.drop_index("ix_query_logs_api_key_id")
        batch.drop_column("api_key_id")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
