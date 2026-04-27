import asyncio
import hashlib
import hmac
import json
import logging
import socket
import ipaddress
from datetime import datetime
from urllib.parse import urlparse

import aio_pika
import httpx
from pydantic import BaseModel

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
    job_id: str
    tenant_id: str
    status: str
    stats: dict | None
    completed_at: str | None
    documents_url: str
    callback_url: str


async def get_mq_connection(url: str):
    return await aio_pika.connect_robust(url)


async def setup_rabbitmq(channel: aio_pika.abc.AbstractChannel):
    exchange = await channel.declare_exchange("webhooks", aio_pika.ExchangeType.DIRECT, durable=True)
    queue = await channel.declare_queue("webhooks", durable=True)
    await queue.bind(exchange, routing_key="webhooks")

    dlx = await channel.declare_exchange("webhooks.dlx", aio_pika.ExchangeType.DIRECT, durable=True)
    dlq = await channel.declare_queue("webhooks.dlq", durable=True)
    await dlq.bind(dlx, routing_key="webhooks.dlq")

    return exchange


async def publish_webhook(rabbitmq_url: str, payload: WebhookPayload):
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
            await exchange.publish(message, routing_key="webhooks")
            logger.info("Published webhook for job %s", payload.job_id)
    except Exception as e:
        logger.error("Failed to publish webhook: %s", e)


def publish_webhook_sync(rabbitmq_url: str, payload: WebhookPayload):
    import threading

    def _run():
        try:
            asyncio.run(publish_webhook(rabbitmq_url, payload))
        except Exception as e:
            logger.error("Error in webhook thread: %s", e)

    threading.Thread(target=_run, daemon=True).start()


async def run_webhook_worker(rabbitmq_url: str, api_key: str):
    connection = await get_mq_connection(rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=10)
        await setup_rabbitmq(channel)

        queue = await channel.get_queue("webhooks")
        dlx = await channel.get_exchange("webhooks.dlx")

        logger.info("Starting webhook worker...")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process(ignore_processed=True):
                    try:
                        retry_count = message.headers.get("x-retry-count", 0)
                        data = json.loads(message.body)
                        callback_url = data.pop("callback_url", None)

                        if not callback_url:
                            await message.ack()
                            continue

                        # SSRF guard — reject private/loopback callback URLs
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
                            "X-Scraper-Signature": f"sha256={signature}",
                        }

                        # Deliver with follow_redirects=False to prevent SSRF via redirect
                        async with httpx.AsyncClient(
                            timeout=10.0, follow_redirects=False
                        ) as client:
                            resp = await client.post(
                                callback_url, content=raw_payload, headers=headers
                            )
                            resp.raise_for_status()

                        await message.ack()
                        logger.info("Delivered webhook for job %s", data.get("job_id"))

                    except Exception as e:
                        logger.warning("Webhook delivery failed: %s", e)
                        if retry_count < 3:
                            delay = [5, 25, 125][retry_count]
                            logger.info("Retrying job %s in %ss", data.get("job_id"), delay)

                            new_msg = aio_pika.Message(
                                body=message.body,
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                headers={"x-retry-count": retry_count + 1},
                            )

                            async def requeue_after(d, exch, msg):
                                await asyncio.sleep(d)
                                await exch.publish(msg, routing_key="webhooks")

                            exchange = await channel.get_exchange("webhooks")
                            asyncio.create_task(requeue_after(delay, exchange, new_msg))
                            await message.ack()
                        else:
                            logger.error(
                                "Webhook failed 3 times, moving to DLQ for job %s",
                                data.get("job_id"),
                            )
                            dlx_msg = aio_pika.Message(
                                body=message.body,
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                headers={"x-death-reason": str(e)},
                            )
                            await dlx.publish(dlx_msg, routing_key="webhooks.dlq")
                            await message.ack()
