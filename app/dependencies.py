# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""FastAPI dependency injection providers."""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

import app.db as _db
from app.services.job_store import JobStore


async def get_db_session() -> AsyncSession:
    """Yield an async SQLAlchemy session scoped to the request."""
    async with _db.async_session_maker() as session:
        yield session  # type: ignore[misc]


async def get_job_store(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JobStore:
    """Build a JobStore wired to the request-scoped DB session and Redis."""
    return JobStore(session=session, redis_client=request.app.state.redis)


__all__ = ["get_db_session", "get_job_store"]
