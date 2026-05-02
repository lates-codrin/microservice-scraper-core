# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""SQLAlchemy ORM models for PostgreSQL persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class DbCrawlJob(Base):
    __tablename__ = "crawl_jobs"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String)

    # Store config, progress, stats, error as JSONB
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    stats: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    callback_url: Mapped[str | None] = mapped_column(String, nullable=True)

    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_completion_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    documents: Mapped[list[DbScrapedDocument]] = relationship(
        "DbScrapedDocument", back_populates="job", cascade="all, delete-orphan"
    )


class DbScrapedDocument(Base):
    __tablename__ = "scraped_documents"

    document_id: Mapped[str] = mapped_column(String, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("crawl_jobs.job_id", ondelete="CASCADE"), index=True
    )
    tenant_id: Mapped[str] = mapped_column(String, index=True)

    source_url: Mapped[str] = mapped_column(String)
    canonical_url: Mapped[str | None] = mapped_column(String, nullable=True)
    mime_type: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)

    raw_text: Mapped[str] = mapped_column(String)
    raw_html: Mapped[str | None] = mapped_column(String, nullable=True)
    binary_url: Mapped[str | None] = mapped_column(String, nullable=True)

    doc_type: Mapped[str] = mapped_column(String)
    doc_type_confidence: Mapped[float] = mapped_column(Float)

    title: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[str] = mapped_column(String)
    published_at: Mapped[str | None] = mapped_column(String, nullable=True)  # or Date
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_length: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String)

    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default={})
    extraction_confidence: Mapped[float] = mapped_column(Float)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=[])

    job: Mapped[DbCrawlJob] = relationship("DbCrawlJob", back_populates="documents")

    __table_args__ = (
        Index("idx_tenant_job_doc_conf", "tenant_id", "job_id", "doc_type", "doc_type_confidence"),
    )
