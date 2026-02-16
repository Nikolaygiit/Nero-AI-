"""
Общий асинхронный Redis-клиент для rate limit и других задач.
При недоступности Redis функции возвращают fallback-поведение.
"""

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

_redis: Optional["Redis"] = None


async def get_redis():
    """Возвращает общий async Redis-клиент или None, если Redis недоступен."""
    global _redis
    if _redis is not None:
        return _redis
    try:
        from redis.asyncio import from_url

        import config

        client = from_url(config.settings.REDIS_URL, decode_responses=True)
        await client.ping()
        _redis = client
        logger.info("redis_connected", url=config.settings.REDIS_URL.split("@")[-1])
        return _redis
    except Exception as e:
        logger.warning("redis_unavailable", error=str(e))
        return None


async def close_redis() -> None:
    """Закрывает соединение с Redis (вызывать при shutdown бота)."""
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("redis_closed")
