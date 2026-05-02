# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Webhook delivery service ” async RabbitMQ worker with HMAC signing.

Spec Â§5 compliance:
  - Header: X-Vendor-Signature: sha256=<hmac>
  - Payload includes `event` and `at` fields
  - 3-attempt exponential back-off (5s, 25s, 125s) before DLQ
  - SSRF guard on callback URLs
  - follow_redirects=False to prevent redirect-based SSRF bypass
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import socket
from urllib.parse import urlparse

import aio_pika
import httpx
from pydantic import BaseModel

from app.constants import (
    WEBHOOK_DLQ,
    WEBHOOK_DLX,
    WEBHOOK_EXCHANGE,
    WEBHOOK_MAX_RETRIES,
    WEBHOOK_QUEUE,
    WEBHOOK_RETRY_DELAYS,
    WEBHOOK_SIGNATURE_HEADER,
)

logger = logging.getLogger(__name__)

_PRIVATE_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class SSRFBlockedError(Exception):
    """Raised when a callback URL resolves to a private/loopback address."""


def _check_callback_ssrf(url: str) -> None:
    """Raise SSRFBlockedError if *url* resolves to a private/loopback/link-local address."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if not hostname:
        raise SSRFBlockedError(f"Empty hostname in callback URL: {url!r}")
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"DNS failed for callback host '{hostname}': {exc}") from exc
    for *_, sockaddr in infos:
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        for net in _PRIVATE_NETS:
            if addr in net:
                raise SSRFBlockedError(
                    f"SSRF: callback host '{hostname}' resolves to private address '{sockaddr[0]}'"
                )


class WebhookPayload(BaseModel):
    """Webhook delivery payload per spec Â§5."""

    event: str
    job_id: str
    tenant_id: str
    status: str
    stats: dict | None = None
    completed_at: str | None = None
    at: str  # ISO-8601 timestamp when event was emitted
    documents_url: str
    callback_url: str


async def get_mq_connection(url: str) -> aio_pika.abc.AbstractRobustConnection:
    """Open a robust RabbitMQ connection."""
    return await aio_pika.connect_robust(url)


async def setup_rabbitmq(
    channel: aio_pika.abc.AbstractChannel,
) -> aio_pika.abc.AbstractExchange:
    """Declare exchange, queue, and DLQ topology."""
    exchange = await channel.declare_exchange(
        WEBHOOK_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
    )
    queue = await channel.declare_queue(WEBHOOK_QUEUE, durable=True)
    await queue.bind(exchange, routing_key=WEBHOOK_QUEUE)

    dlx = await channel.declare_exchange(WEBHOOK_DLX, aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue(WEBHOOK_DLQ, durable=True)
    await dlq.bind(dlx, routing_key=WEBHOOK_DLQ)

    return exchange


async def publish_webhook(rabbitmq_url: str, payload: WebhookPayload) -> None:
    """Publish a webhook message to RabbitMQ."""
    try:
        connection = await get_mq_connection(rabbitmq_url)
        async with connection:
            channel = await connection.channel()
            exchange = await setup_rabbitmq(channel)

            message = aio_pika.Message(
                body=payload.model_dump_json().encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                headers={"x-retry-count": 0},
            )
            await exchange.publish(message, routing_key=WEBHOOK_QUEUE)
            logger.info("Published webhook for job %s", payload.job_id)
    except Exception:
        logger.exception("Failed to publish webhook for job %s", payload.job_id)


async def run_webhook_worker(rabbitmq_url: str, api_key: str) -> None:
    """Long-running worker that delivers webhooks with HMAC signing.

    Retry policy: 3 attempts with exponential back-off (5s, 25s, 125s).
    Failed messages after exhausting retries are moved to the DLQ.
    """
    connection = await get_mq_connection(rabbitmq_url)
    # Track fire-and-forget requeue tasks to prevent silent GC
    _background_tasks: set[asyncio.Task[None]] = set()

    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        await setup_rabbitmq(channel)

        queue = await channel.get_queue(WEBHOOK_QUEUE)
        dlx = await channel.get_exchange(WEBHOOK_DLX)

        logger.info("Webhook worker started")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process(ignore_processed=True):
                    try:
                        retry_count: int = message.headers.get("x-retry-count", 0)
                        data = json.loads(message.body)
                        callback_url = data.pop("callback_url", None)

                        if not callback_url:
                            await message.ack()
                            continue

                        # SSRF guard
                        try:
                            _check_callback_ssrf(callback_url)
                        except SSRFBlockedError as ssrf_exc:
                            logger.error(
                                "Webhook SSRF blocked for job %s: %s",
                                data.get("job_id"),
                                ssrf_exc,
                            )
                            await message.ack()
                            continue

                        raw_payload = json.dumps(data)
                        signature = hmac.new(
                            api_key.encode("utf-8"),
                            raw_payload.encode("utf-8"),
                            hashlib.sha256,
                        ).hexdigest()

                        headers = {
                            "Content-Type": "application/json",
                            WEBHOOK_SIGNATURE_HEADER: f"sha256={signature}",
                        }

                        # Deliver with follow_redirects=False to prevent
                        # SSRF via redirect
                        async with httpx.AsyncClient(
                            timeout=10.0, follow_redirects=False
                        ) as client:
                            resp = await client.post(
                                callback_url,
                                content=raw_payload,
                                headers=headers,
                            )
                            resp.raise_for_status()

                        await message.ack()
                        logger.info(
                            "Delivered webhook for job %s",
                            data.get("job_id"),
                        )

                    except Exception as exc:
                        logger.warning("Webhook delivery failed: %s", exc)
                        if retry_count < WEBHOOK_MAX_RETRIES:
                            delay = WEBHOOK_RETRY_DELAYS[retry_count]
                            logger.info(
                                "Retrying job %s in %ss",
                                data.get("job_id"),
                                delay,
                            )

                            new_msg = aio_pika.Message(
                                body=message.body,
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                headers={
                                    "x-retry-count": retry_count + 1,
                                },
                            )

                            async def _requeue_after(
                                delay_seconds: int,
                                exch: aio_pika.abc.AbstractExchange,
                                msg: aio_pika.Message,
                            ) -> None:
                                await asyncio.sleep(delay_seconds)
                                await exch.publish(msg, routing_key=WEBHOOK_QUEUE)

                            exchange = await channel.get_exchange(WEBHOOK_EXCHANGE)
                            task = asyncio.create_task(_requeue_after(delay, exchange, new_msg))
                            _background_tasks.add(task)
                            task.add_done_callback(_background_tasks.discard)
                            await message.ack()
                        else:
                            logger.error(
                                "Webhook failed %d times, moving to DLQ for job %s",
                                WEBHOOK_MAX_RETRIES,
                                data.get("job_id"),
                            )
                            dlx_msg = aio_pika.Message(
                                body=message.body,
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                headers={"x-death-reason": str(exc)},
                            )
                            await dlx.publish(dlx_msg, routing_key=WEBHOOK_DLQ)
                            await message.ack()


__all__ = [
    "SSRFBlockedError",
    "WebhookPayload",
    "get_mq_connection",
    "publish_webhook",
    "run_webhook_worker",
    "setup_rabbitmq",
]
