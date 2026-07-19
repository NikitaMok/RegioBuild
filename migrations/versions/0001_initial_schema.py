"""initial schema: documents, chunks, query_logs

Revision ID: 0001
Revises:
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("region_code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("local_raw_path", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_region_code", "documents", ["region_code"])

    op.create_table(
        "chunks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("region_code", sa.String(length=64), nullable=False),
        sa.Column("section_number", sa.String(length=64), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("vector_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_region_code", "chunks", ["region_code"])
    op.create_index("ix_chunks_category", "chunks", ["category"])
    op.create_index("ix_chunks_vector_id", "chunks", ["vector_id"])

    op.create_table(
        "query_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("region_a", sa.String(length=64), nullable=False),
        sa.Column("region_b", sa.String(length=64), nullable=True),
        sa.Column("business_type", sa.String(length=128), nullable=True),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("query_logs")
    op.drop_index("ix_chunks_vector_id", table_name="chunks")
    op.drop_index("ix_chunks_category", table_name="chunks")
    op.drop_index("ix_chunks_region_code", table_name="chunks")
    op.drop_index("ix_chunks_document_id", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_documents_region_code", table_name="documents")
    op.drop_table("documents")
