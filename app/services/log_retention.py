# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Log retention and cleanup service — GDPR compliance."""

from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


class LogRetentionPolicy:
    """Manages log retention and cleanup per spec §7.3 — 7-day maximum retention."""

    def __init__(
        self,
        retention_days: int = 7,
        cleanup_interval_hours: int = 24,
    ):
        """Initialize retention policy.
        
        Args:
            retention_days: Max days to retain logs (default: 7 per spec)
            cleanup_interval_hours: How often to run cleanup (default: daily)
        """
        self.retention_days = retention_days
        self.cleanup_interval_hours = cleanup_interval_hours
        self.cleanup_task: asyncio.Task | None = None

    def get_retention_cutoff(self) -> datetime:
        """Get the cutoff datetime beyond which logs should be deleted."""
        return datetime.utcnow() - timedelta(days=self.retention_days)

    async def cleanup_old_logs(self, job_store: Any) -> int:
        """Delete logs and job data older than retention period.
        
        Args:
            job_store: JobStore instance for database cleanup
            
        Returns:
            Number of records deleted
        """
        cutoff = self.get_retention_cutoff()
        deleted_count = 0
        
        try:
            # Delete old jobs from database
            deleted_count = await job_store.delete_jobs_before(cutoff)
            logger.info(
                "Log retention: deleted %d jobs before %s",
                deleted_count,
                cutoff.isoformat(),
            )
        except Exception as exc:
            logger.error("Log cleanup failed: %s", exc)
            
        return deleted_count

    async def start_cleanup_task(self, job_store: Any) -> None:
        """Start background cleanup task.
        
        Args:
            job_store: JobStore instance for cleanup operations
        """
        async def cleanup_loop():
            while True:
                await asyncio.sleep(self.cleanup_interval_hours * 3600)
                await self.cleanup_old_logs(job_store)

        if self.cleanup_task is None or self.cleanup_task.done():
            self.cleanup_task = asyncio.create_task(cleanup_loop())
            logger.info(
                "Log retention cleanup task started (retention=%d days)",
                self.retention_days,
            )

    async def stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self.cleanup_task and not self.cleanup_task.done():
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Log retention cleanup task stopped")


# Global retention policy instance
_retention_policy = LogRetentionPolicy(retention_days=7, cleanup_interval_hours=24)


def get_retention_policy() -> LogRetentionPolicy:
    """Get global retention policy."""
    return _retention_policy
