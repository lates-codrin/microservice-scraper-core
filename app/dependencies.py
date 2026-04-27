from fastapi import Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import redis

from app.services.job_store import JobStore
from app.db import get_db_session


def get_job_store(
    session: AsyncSession = Depends(get_db_session),
    request: Request = None
) -> JobStore:
    # Redis is on app state
    redis_client = request.app.state.redis
    return JobStore(session, redis_client)