# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Job lifecycle state machine ” enforces valid status transitions."""

from __future__ import annotations

from app.models.enums import CrawlStatus

# Mapping: current_status  set of valid next statuses.
_VALID_TRANSITIONS: dict[CrawlStatus, frozenset[CrawlStatus]] = {
    CrawlStatus.queued: frozenset(
        {
            CrawlStatus.fetching_sitemap,
            CrawlStatus.crawling,
            CrawlStatus.failed,
            CrawlStatus.cancelled,
            # scrape jobs skip directly to done
            CrawlStatus.done,
        }
    ),
    CrawlStatus.fetching_sitemap: frozenset(
        {
            CrawlStatus.crawling,
            CrawlStatus.failed,
            CrawlStatus.cancelled,
        }
    ),
    CrawlStatus.crawling: frozenset(
        {
            CrawlStatus.extracting,
            CrawlStatus.done,
            CrawlStatus.failed,
            CrawlStatus.cancelled,
            CrawlStatus.partial,
        }
    ),
    CrawlStatus.extracting: frozenset(
        {
            CrawlStatus.classifying,
            CrawlStatus.done,
            CrawlStatus.failed,
            CrawlStatus.cancelled,
            CrawlStatus.partial,
        }
    ),
    CrawlStatus.classifying: frozenset(
        {
            CrawlStatus.done,
            CrawlStatus.failed,
            CrawlStatus.cancelled,
            CrawlStatus.partial,
        }
    ),
    # Terminal states ” no further transitions.
    CrawlStatus.done: frozenset(),
    CrawlStatus.failed: frozenset(),
    CrawlStatus.cancelled: frozenset(),
    CrawlStatus.partial: frozenset(),
}


class InvalidTransitionError(Exception):
    """Raised when a job status transition violates the state machine."""

    def __init__(
        self,
        job_id: str,
        current: CrawlStatus,
        requested: CrawlStatus,
    ) -> None:
        super().__init__(
            f"Invalid transition for job '{job_id}': '{current.value}'  '{requested.value}'"
        )
        self.job_id = job_id
        self.current = current
        self.requested = requested


def validate_transition(
    job_id: str,
    current: CrawlStatus,
    requested: CrawlStatus,
) -> None:
    """Raise InvalidTransitionError if *current  requested* is invalid."""
    valid_next = _VALID_TRANSITIONS.get(current, frozenset())
    if requested not in valid_next:
        raise InvalidTransitionError(job_id, current, requested)


__all__ = [
    "InvalidTransitionError",
    "validate_transition",
]
