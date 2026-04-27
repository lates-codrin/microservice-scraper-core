import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime

import aio_pika
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
    # Main exchange
    exchange = await channel.declare_exchange("webhooks", aio_pika.ExchangeType.DIRECT, durable=True)
    queue = await channel.declare_queue("webhooks", durable=True)
    await queue.bind(exchange, routing_key="webhooks")

    # DLQ exchange and queue
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
                headers={"x-retry-count": 0}
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
        # Set prefetch count
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
                            # Discard if no callback URL
                            await message.ack()
                            continue

                        # Construct X-Scraper-Signature
                        raw_payload = json.dumps(data)
                        signature = hmac.new(
                            api_key.encode("utf-8"),
                            raw_payload.encode("utf-8"),
                            hashlib.sha256
                        ).hexdigest()

                        headers = {
                            "Content-Type": "application/json",
                            "X-Scraper-Signature": f"sha256={signature}"
                        }

                        async with httpx.AsyncClient(timeout=10.0) as client:
                            resp = await client.post(callback_url, content=raw_payload, headers=headers)
                            resp.raise_for_status()

                        await message.ack()
                        logger.info("Delivered webhook for job %s", data.get("job_id"))

                    except Exception as e:
                        logger.warning("Webhook delivery failed: %s", e)
                        if retry_count < 3:
                            # Requeue with backoff using asyncio.sleep or DLX with TTL
                            # For simplicity, we delay via asyncio.sleep here
                            delay = [5, 25, 125][retry_count]
                            logger.info("Retrying job %s in %ss", data.get("job_id"), delay)
                            
                            # Publish back to the queue with incremented retry count
                            new_msg = aio_pika.Message(
                                body=message.body,
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                headers={"x-retry-count": retry_count + 1}
                            )
                            # Ack original message and publish new one after delay
                            # Wait, sleeping in the worker block blocks other messages if we sleep.
                            # We should ideally spawn a task or use RabbitMQ delayed message plugin.
                            # Spawning a task is fine for our worker.
                            
                            async def requeue_after(d, exch, msg):
                                await asyncio.sleep(d)
                                await exch.publish(msg, routing_key="webhooks")
                                
                            exchange = await channel.get_exchange("webhooks")
                            asyncio.create_task(requeue_after(delay, exchange, new_msg))
                            await message.ack()
                        else:
                            # Move to DLQ
                            logger.error("Webhook failed 3 times, moving to DLQ for job %s", data.get("job_id"))
                            dlx_msg = aio_pika.Message(
                                body=message.body,
                                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                                headers={"x-death-reason": str(e)}
                            )
                            await dlx.publish(dlx_msg, routing_key="webhooks.dlq")
                            await message.ack()
