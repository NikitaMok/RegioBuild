from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def new_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    region_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    local_raw_path: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True, nullable=False)
    region_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    section_number: Mapped[str] = mapped_column(String(64), nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)  # id в Chroma
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped["Document"] = relationship(back_populates="chunks")


class ApiKey(Base):
    """Ключ клиента для коммерческого контура /api/v1."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    client_name: Mapped[str] = mapped_column(String(128), nullable=False)
    daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None → дефолт
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QueryLog(Base):
    """Лог запросов и фидбека."""

    __tablename__ = "query_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # "info" | "compare"
    region_a: Mapped[str] = mapped_column(String(64), nullable=False)
    region_b: Mapped[str] = mapped_column(String(64), nullable=True)
    business_type: Mapped[str] = mapped_column(String(128), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=True)
    answer: Mapped[str] = mapped_column(Text, nullable=True)
    feedback: Mapped[str] = mapped_column(String(8), nullable=True)  # "up" | "down" | None
    telegram_user_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    api_key_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)
    client_ip: Mapped[str] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str] = mapped_column(String(256), nullable=True)
    error_text: Mapped[str] = mapped_column(Text, nullable=True)
    retrieved_sections: Mapped[list | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
