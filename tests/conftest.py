"""
Root conftest: patches the async SQLAlchemy engine to use NullPool during tests.

asyncpg connections are bound to the event loop that created them.  The
synchronous TestClient spins up a fresh event loop for every test, so a
pooled connection from a previous test's loop raises
  "RuntimeError: ... got Future ... attached to a different loop"
Using NullPool (no persistent pool) means each DB operation creates and
immediately closes its own connection, so there is no cross-loop state.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool


@pytest.fixture(scope="session", autouse=True)
def patch_engine_nullpool():
    """Replace the module-level engine in app.db with a NullPool engine."""
    import app.db as db_module
    from app.settings import settings

    null_engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        echo=False,
    )
    null_session_maker = async_sessionmaker(
        bind=null_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    original_engine = db_module.engine
    original_session_maker = db_module.async_session_maker

    db_module.engine = null_engine
    db_module.async_session_maker = null_session_maker

    yield

    db_module.engine = original_engine
    db_module.async_session_maker = original_session_maker
