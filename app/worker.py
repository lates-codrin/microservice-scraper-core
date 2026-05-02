# Copyright 2026 Lates Codrin-Gabriel (https://github.com/lates-codrin)
# SPDX-License-Identifier: Apache-2.0 WITH Commons-Clause-1.0
"""Background worker entry point for webhook delivery."""

import asyncio
import logging

from app.services.webhooks import run_webhook_worker
from app.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting webhook worker process...")
    try:
        asyncio.run(run_webhook_worker(settings.rabbitmq_url, settings.api_key))
    except KeyboardInterrupt:
        logger.info("Worker stopped.")
