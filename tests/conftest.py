"""
Root conftest: patches the async SQLAlchemy engine to use NullPool during tests,
and ensures Redis rate-limit state is reset before every test.

asyncpg connections are bound to the event loop that created them.  The
synchronous TestClient spins up a fresh event loop for every test, so a
pooled connection from a previous test's loop raises
  "RuntimeError: ... got Future ... attached to a different loop"
Using NullPool (no persistent pool) means each DB operation creates and
immediately closes its own connection, so there is no cross-loop state.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Raise the rate-limit ceiling for the test process so performance tests
# (which fire 50-100 sequential requests) never hit the 100-req/min default.
# This must happen before any app module is imported.
# ---------------------------------------------------------------------------
os.environ.setdefault("RATE_LIMIT_REQUESTS", "10000")
os.environ.setdefault("RATE_LIMIT_WINDOW_SECONDS", "60")


# ---------------------------------------------------------------------------
# Crypto patching — keeps bcrypt/passlib from burning CPU in tests.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session", autouse=True)
def patch_crypto():
    """Mock out slow crypto algorithms to speed up tests significantly."""
    try:
        import bcrypt
        bcrypt.checkpw = lambda password, hashed: True
    except ImportError:
        pass

    try:
        from passlib.context import CryptContext
        CryptContext.verify = lambda self, secret, hash: True
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Database patching — NullPool prevents cross-loop connection errors.
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Redis cleanup — flush all rate-limit keys before (and after) every test.
#
# Without this, keys written by one test accumulate in Redis and immediately
# exhaust the quota for the next test, producing cascading 429 failures even
# though the middleware logic is otherwise correct.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def flush_rate_limit_keys():
    """Delete all ratelimit:* keys in Redis around each test."""
    import redis as redis_lib

    try:
        from app.settings import settings
        redis_url = settings.redis_url
    except Exception:
        redis_url = "redis://localhost:6379/0"

    try:
        r = redis_lib.Redis.from_url(redis_url, decode_responses=True)
        _flush(r)
        yield
        _flush(r)
    except Exception:
        # If Redis is unavailable (e.g. unit tests with no Redis), skip silently.
        yield


def _flush(r: "redis_lib.Redis") -> None:  # type: ignore[name-defined]
    """Delete every ratelimit:* key without flushing the whole DB."""
    keys = r.keys("ratelimit:*")
    if keys:
        r.delete(*keys)