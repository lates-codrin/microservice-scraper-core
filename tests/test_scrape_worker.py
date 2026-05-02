from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.scrape_runner import _run_job


class _DummySession:
    pass


@asynccontextmanager
async def _fake_session_maker():
    yield _DummySession()


@pytest.mark.asyncio
async def test_scrape_worker_reconstructs_payload(monkeypatch):
    execute = AsyncMock(return_value=None)
    monkeypatch.setattr("app.scrape_runner.async_session_maker", _fake_session_maker)
    monkeypatch.setattr("app.scrape_runner.execute_sync_scrape", execute)

    job = SimpleNamespace(
        job_id="sj_123",
        tenant_id="tenant-x",
        config={
            "url": "https://example.com/doc",
            "mode": "async",
            "classify": True,
        },
    )

    await _run_job(job, sync_redis=object(), async_redis=object())

    execute.assert_awaited_once()
    call_args = execute.await_args.kwargs
    assert call_args["job_id"] == "sj_123"
    assert call_args["tenant_id"] == "tenant-x"
    assert str(call_args["payload"].url) == "https://example.com/doc"
    assert call_args["payload"].mode == "async"
