# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Abstract interfaces for service layer ” enables DIP and drop-in swapping."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.crawl import CrawlConfig, CrawlJob, CrawlProgress, CrawlStats, IncrementalOptions
from app.models.document import ScrapedDocument
from app.models.enums import CrawlStatus, DocType


class JobStoreProtocol(ABC):
    """Persistence contract for crawl/scrape jobs."""

    @abstractmethod
    async def create_crawl_job(
        self,
        tenant_id: str,
        config: CrawlConfig,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        incremental: IncrementalOptions | None = None,
        callback_url: Any | None = None,
    ) -> CrawlJob:
        ...

    @abstractmethod
    async def create_scrape_job(
        self,
        tenant_id: str,
        request_payload: dict[str, Any] | None = None,
    ) -> str:
        ...

    @abstractmethod
    async def get(self, job_id: str, tenant_id: str | None = None) -> CrawlJob | None:
        ...

    @abstractmethod
    async def update(
        self,
        job_id: str,
        *,
        status: CrawlStatus | None = None,
        progress: CrawlProgress | None = None,
        stats: CrawlStats | None = None,
        error: dict[str, Any] | None = None,
    ) -> CrawlJob | None:
        ...

    @abstractmethod
    async def delete(self, job_id: str) -> bool:
        ...

    @abstractmethod
    async def cancel_job(self, job_id: str) -> CrawlJob | None:
        ...

    @abstractmethod
    async def document_count(self, job_id: str) -> int:
        ...

    @abstractmethod
    async def get_documents(
        self,
        job_id: str,
        *,
        cursor: str | None,
        limit: int,
        doc_type: str | None,
        min_confidence: float,
        changed_only: bool = False,
    ) -> tuple[list[ScrapedDocument], str | None, bool, int]:
        ...

    @abstractmethod
    async def add_document(
        self, job_id: str, tenant_id: str, document: ScrapedDocument
    ) -> None:
        ...

    @abstractmethod
    async def queue_depth(self) -> int:
        ...


class ClassifierProtocol(ABC):
    """Contract for document type classification."""

    @abstractmethod
    def classify(
        self,
        url: str | None,
        text: str,
    ) -> tuple[DocType, float, list[dict[str, Any]]]:
        ...


class FieldExtractorProtocol(ABC):
    """Contract for structured field extraction."""

    @abstractmethod
    def extract_fields(
        self,
        text: str,
        doc_type: DocType,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        ...


class ExtractorProtocol(ABC):
    """Contract for content extraction from raw bytes."""

    @abstractmethod
    def can_handle(self, mime_type: str) -> bool:
        ...

    @abstractmethod
    def extract(
        self, content: bytes, source_url: str = ""
    ) -> Any:
        ...


__all__ = [
    "ClassifierProtocol",
    "ExtractorProtocol",
    "FieldExtractorProtocol",
    "JobStoreProtocol",
]

