"""Taskiq broker — Redis. Очереди задач для тяжёлых операций (генерация изображений и т.д.)."""
import logging
from typing import Optional

from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

import config

logger = logging.getLogger(__name__)

# Имя ключа очереди в Redis (ListQueueBroker хранит список под этим ключом; при смене — задать TASKIQ_QUEUE_NAME в .env)
TASKIQ_DEFAULT_QUEUE = getattr(config.settings, "TASKIQ_QUEUE_NAME", None) or "default"

broker: Optional[ListQueueBroker] = None
try:
    broker = ListQueueBroker(url=config.settings.REDIS_URL)
    broker.result_backend = RedisAsyncResultBackend(config.settings.REDIS_URL)
except Exception as e:
    logger.warning("Redis недоступен, фоновые задачи отключены: %s", e)


async def get_taskiq_queue_length() -> int:
    """
    Возвращает количество задач в очереди Taskiq (для сообщения «ваша позиция в очереди: N»).
    При ошибке (Redis недоступен) возвращает 0.
    """
    try:
        from redis.asyncio import from_url
        client = from_url(config.settings.REDIS_URL)
        try:
            return await client.llen(TASKIQ_DEFAULT_QUEUE)
        finally:
            await client.aclose()
    except Exception:
        return 0
