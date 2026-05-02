# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Tests for webhook delivery: HMAC signing, retries, DLQ."""

import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.constants import WEBHOOK_SIGNATURE_HEADER
from app.services.webhooks import WebhookPayload, run_webhook_worker


@pytest.fixture
def mock_rabbitmq():
    with patch("app.services.webhooks.get_mq_connection") as mock_conn:
        mock_connection = AsyncMock()
        mock_channel = AsyncMock()
        mock_exchange = AsyncMock()
        mock_queue = AsyncMock()
        mock_dlx = AsyncMock()

        mock_conn.return_value = mock_connection
        mock_connection.channel.return_value = mock_channel
        mock_channel.declare_exchange.return_value = mock_exchange
        mock_channel.declare_queue.return_value = mock_queue
        mock_channel.get_queue.return_value = mock_queue
        mock_channel.get_exchange.return_value = mock_dlx

        class MockIteratorContextManager:
            async def __aenter__(self):
                return getattr(mock_queue, "_iterator_obj", [])

            async def __aexit__(self, exc_type, exc, tb):
                pass

        mock_queue.iterator = MagicMock(return_value=MockIteratorContextManager())

        yield mock_conn, mock_connection, mock_channel, mock_queue, mock_dlx


@pytest.fixture
def mock_httpx():
    with patch("httpx.AsyncClient.post") as mock_post:
        yield mock_post


def _make_payload(**overrides) -> WebhookPayload:
    """Build a WebhookPayload with default values for all required fields."""
    defaults = {
        "event": "crawl.completed",
        "job_id": "test_job",
        "tenant_id": "tenant_1",
        "status": "done",
        "stats": {},
        "completed_at": "2026-04-22T10:34:12Z",
        "at": "2026-04-22T10:34:12Z",
        "documents_url": "http://localhost/docs",
        "callback_url": "http://example.com/webhook",
    }
    defaults.update(overrides)
    return WebhookPayload(**defaults)


@pytest.mark.asyncio
async def test_webhook_worker_success(mock_rabbitmq, mock_httpx):
    mock_conn, mock_connection, mock_channel, mock_queue, mock_dlx = mock_rabbitmq

    payload = _make_payload()
    mock_msg = AsyncMock()
    mock_msg.headers = {"x-retry-count": 0}
    mock_msg.body = payload.model_dump_json().encode()

    class MockProcessContextManager:
        async def __aenter__(self):
            return mock_msg

        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_msg.process = MagicMock(return_value=MockProcessContextManager())

    async def mock_iterator_gen():
        yield mock_msg

    mock_queue._iterator_obj = mock_iterator_gen()

    mock_resp = AsyncMock()
    mock_resp.raise_for_status.return_value = None
    mock_httpx.return_value = mock_resp

    api_key = "test_api_key"
    await run_webhook_worker("amqp://dummy", api_key)

    mock_httpx.assert_called_once()
    args, kwargs = mock_httpx.call_args
    assert args[0] == "http://example.com/webhook"

    req_body = kwargs["content"]
    expected_sig = hmac.new(api_key.encode(), req_body.encode(), hashlib.sha256).hexdigest()

    assert kwargs["headers"][WEBHOOK_SIGNATURE_HEADER] == f"sha256={expected_sig}"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    mock_msg.ack.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_worker_retry_on_failure(mock_rabbitmq, mock_httpx):
    mock_conn, mock_connection, mock_channel, mock_queue, mock_dlx = mock_rabbitmq

    payload = _make_payload()
    mock_msg = AsyncMock()
    mock_msg.headers = {"x-retry-count": 0}
    mock_msg.body = payload.model_dump_json().encode()

    class MockProcessContextManager:
        async def __aenter__(self):
            return mock_msg

        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_msg.process = MagicMock(return_value=MockProcessContextManager())

    async def mock_iterator_gen():
        yield mock_msg

    mock_queue._iterator_obj = mock_iterator_gen()

    import httpx

    mock_httpx.side_effect = httpx.HTTPStatusError(
        "Error", request=MagicMock(), response=MagicMock()
    )

    with patch("asyncio.create_task") as mock_create_task:
        await run_webhook_worker("amqp://dummy", "test_api_key")

        mock_httpx.assert_called_once()
        mock_msg.ack.assert_called_once()
        mock_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_webhook_worker_dlq_after_3_failures(mock_rabbitmq, mock_httpx):
    mock_conn, mock_connection, mock_channel, mock_queue, mock_dlx = mock_rabbitmq

    payload = _make_payload()
    mock_msg = AsyncMock()
    mock_msg.headers = {"x-retry-count": 3}
    mock_msg.body = payload.model_dump_json().encode()

    class MockProcessContextManager:
        async def __aenter__(self):
            return mock_msg

        async def __aexit__(self, exc_type, exc, tb):
            pass

    mock_msg.process = MagicMock(return_value=MockProcessContextManager())

    async def mock_iterator_gen():
        yield mock_msg

    mock_queue._iterator_obj = mock_iterator_gen()

    import httpx

    mock_httpx.side_effect = httpx.HTTPStatusError(
        "Error", request=MagicMock(), response=MagicMock()
    )

    await run_webhook_worker("amqp://dummy", "test_api_key")

    mock_httpx.assert_called_once()
    mock_dlx.publish.assert_called_once()
    mock_msg.ack.assert_called_once()
