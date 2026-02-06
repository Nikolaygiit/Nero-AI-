"""Taskiq broker — Redis"""
import logging
from typing import Optional

from taskiq_redis import RedisAsyncResultBackend, ListQueueBroker

import config

logger = logging.getLogger(__name__)

broker: Optional[ListQueueBroker] = None
try:
    broker = ListQueueBroker(url=config.settings.REDIS_URL)
    broker.result_backend = RedisAsyncResultBackend(config.settings.REDIS_URL)
except Exception as e:
    logger.warning("Redis недоступен, фоновые задачи отключены: %s", e)
