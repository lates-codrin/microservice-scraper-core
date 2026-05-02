"""initial schema

Revision ID: 6302e90916f4
Revises:
Create Date: 2026-04-27 15:43:44.617024

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6302e90916f4"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "crawl_jobs",
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("progress", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stats", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("callback_url", sa.String(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_completion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_index(op.f("ix_crawl_jobs_tenant_id"), "crawl_jobs", ["tenant_id"], unique=False)

    op.create_table(
        "scraped_documents",
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("job_id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("canonical_url", sa.String(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("raw_text", sa.String(), nullable=False),
        sa.Column("raw_html", sa.String(), nullable=True),
        sa.Column("binary_url", sa.String(), nullable=True),
        sa.Column("doc_type", sa.String(), nullable=False),
        sa.Column("doc_type_confidence", sa.Float(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("language", sa.String(), nullable=False),
        sa.Column("published_at", sa.String(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("content_length", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(), nullable=False),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=False),
        sa.Column("warnings", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["crawl_jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id"),
    )
    op.create_index(
        op.f("ix_scraped_documents_job_id"), "scraped_documents", ["job_id"], unique=False
    )
    op.create_index(
        op.f("ix_scraped_documents_tenant_id"), "scraped_documents", ["tenant_id"], unique=False
    )
    op.create_index(
        "idx_tenant_job_doc_conf",
        "scraped_documents",
        ["tenant_id", "job_id", "doc_type", "doc_type_confidence"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_tenant_job_doc_conf", table_name="scraped_documents")
    op.drop_index(op.f("ix_scraped_documents_tenant_id"), table_name="scraped_documents")
    op.drop_index(op.f("ix_scraped_documents_job_id"), table_name="scraped_documents")
    op.drop_table("scraped_documents")
    op.drop_index(op.f("ix_crawl_jobs_tenant_id"), table_name="crawl_jobs")
    op.drop_table("crawl_jobs")
