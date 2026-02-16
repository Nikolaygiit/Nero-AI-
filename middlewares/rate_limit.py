"""
Middleware для rate limiting.
При наличии Redis — общий лимит для всех инстансов бота (sliding window).
При недоступности Redis — fallback на in-memory (только для одного процесса).
"""

import logging
import time
from collections import defaultdict
from typing import Dict

from telegram import Update
from telegram.ext import ContextTypes

import config

logger = logging.getLogger(__name__)

# In-memory fallback: {user_id: [timestamps]}
_user_requests: Dict[int, list] = defaultdict(list)

# Префикс ключа в Redis для rate limit (sliding window)
RATE_LIMIT_KEY_PREFIX = "rl:"


class RateLimitMiddleware:
    """Middleware для ограничения частоты запросов (Redis или in-memory)."""

    def __init__(self, max_requests: int = None, time_window: int = 60):
        """
        Args:
            max_requests: Максимальное количество запросов за time_window секунд
            time_window: Окно времени в секундах (по умолчанию 60 секунд = 1 минута)
        """
        self.max_requests = max_requests or config.RATE_LIMIT_PER_USER
        self.time_window = time_window

    async def _check_redis(self, user_id: int) -> bool:
        """
        Проверка лимита через Redis (sliding window).
        Returns: True если запрос разрешён, False если лимит превышен.
        """
        try:
            from utils.redis_client import get_redis

            redis = await get_redis()
            if redis is None:
                return self._check_memory_sync(user_id)

            key = f"{RATE_LIMIT_KEY_PREFIX}{user_id}"
            now = time.time()
            window_start = now - self.time_window

            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, self.time_window + 10)
            results = await pipe.execute()

            count_after_removal = results[1]
            if count_after_removal >= self.max_requests:
                return False
            return True
        except Exception as e:
            logger.warning("rate_limit_redis_error", user_id=user_id, error=str(e))
            return self._check_memory_sync(user_id)

    def _check_memory_sync(self, user_id: int) -> bool:
        """In-memory проверка (синхронная, для fallback)."""
        current_time = time.time()
        user_requests = _user_requests[user_id]
        _user_requests[user_id] = [
            ts for ts in user_requests if current_time - ts < self.time_window
        ]
        if len(_user_requests[user_id]) >= self.max_requests:
            return False
        _user_requests[user_id].append(current_time)
        return True

    async def check_rate_limit(self, user_id: int) -> bool:
        """
        Проверяет, не превышен ли лимит запросов для пользователя.
        Сначала пробует Redis, при ошибке — in-memory.

        Returns:
            True если запрос разрешен, False если лимит превышен
        """
        try:
            return await self._check_redis(user_id)
        except Exception as e:
            logger.warning("rate_limit_fallback", user_id=user_id, error=str(e))
            return self._check_memory_sync(user_id)

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE, next_handler):
        """Вызывается перед обработчиком"""
        user_id = update.effective_user.id

        if not await self.check_rate_limit(user_id):
            if update.message:
                await update.message.reply_text(
                    f"⏳ Слишком много запросов. Подождите {self.time_window} секунд.\n\n"
                    f"💡 Лимит: {self.max_requests} запросов в минуту",
                    parse_mode=None,
                )
            elif update.callback_query:
                await update.callback_query.answer(
                    f"⏳ Слишком много запросов. Подождите {self.time_window} секунд.",
                    show_alert=True,
                )
            return

        return await next_handler(update, context)


rate_limit_middleware = RateLimitMiddleware()
