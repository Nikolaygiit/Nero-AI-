"""
Middleware для rate limiting
"""

import logging
import time
from collections import defaultdict
from typing import Dict

from telegram import Update
from telegram.ext import ContextTypes

import config

logger = logging.getLogger(__name__)

# Хранилище запросов пользователей: {user_id: [timestamps]}
user_requests: Dict[int, list] = defaultdict(list)


class RateLimitMiddleware:
    """Middleware для ограничения частоты запросов"""

    def __init__(self, max_requests: int = None, time_window: int = 60):
        """
        Args:
            max_requests: Максимальное количество запросов за time_window секунд
            time_window: Окно времени в секундах (по умолчанию 60 секунд = 1 минута)
        """
        self.max_requests = max_requests or config.RATE_LIMIT_PER_USER
        self.time_window = time_window

    async def check_rate_limit(self, user_id: int) -> bool:
        """
        Проверяет, не превышен ли лимит запросов для пользователя

        Returns:
            True если запрос разрешен, False если лимит превышен
        """
        current_time = time.time()

        # Очищаем старые запросы (старше time_window секунд)
        user_requests[user_id] = [
            timestamp
            for timestamp in user_requests[user_id]
            if current_time - timestamp < self.time_window
        ]

        # Проверяем лимит
        if len(user_requests[user_id]) >= self.max_requests:
            logger.warning(f"Rate limit превышен для пользователя {user_id}")
            return False

        # Добавляем текущий запрос
        user_requests[user_id].append(current_time)
        return True

    async def __call__(self, update: Update, context: ContextTypes.DEFAULT_TYPE, next_handler):
        """Вызывается перед обработчиком"""
        user_id = update.effective_user.id

        if not await self.check_rate_limit(user_id):
            # Лимит превышен
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

        # Передаем управление следующему обработчику
        return await next_handler(update, context)


# Глобальный экземпляр middleware
rate_limit_middleware = RateLimitMiddleware()
