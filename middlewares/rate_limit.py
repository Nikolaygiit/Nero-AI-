"""
Middleware для rate limiting
"""
import time
from collections import OrderedDict
from typing import Dict
from telegram import Update
from telegram.ext import ContextTypes
import logging
import config

logger = logging.getLogger(__name__)

# Хранилище запросов пользователей: {user_id: [timestamps]}
user_requests: OrderedDict[int, list] = OrderedDict()


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
    
    def _incremental_prune(self, current_time: float, prune_count: int = 10):
        """
        Удаляет неактивных пользователей из начала OrderedDict.
        Поскольку активные пользователи перемещаются в конец, неактивные скапливаются в начале.
        """
        count = 0
        while user_requests and count < prune_count:
            # Берем самого старого пользователя (первый в OrderedDict)
            uid = next(iter(user_requests))
            timestamps = user_requests[uid]

            # Если последняя активность пользователя была дольше чем time_window назад, удаляем его
            if not timestamps or (current_time - timestamps[-1] >= self.time_window):
                user_requests.popitem(last=False)
            else:
                # Если самый старый пользователь все еще активен, значит остальные и подавно
                break
            count += 1

    async def check_rate_limit(self, user_id: int) -> bool:
        """
        Проверяет, не превышен ли лимит запросов для пользователя
        
        Returns:
            True если запрос разрешен, False если лимит превышен
        """
        current_time = time.time()
        
        # Инкрементальная очистка неактивных пользователей для предотвращения утечки памяти
        self._incremental_prune(current_time)

        # Получаем метки времени пользователя или пустой список
        timestamps = user_requests.get(user_id, [])

        # Очищаем старые запросы текущего пользователя (старше time_window секунд)
        active_timestamps = [
            timestamp for timestamp in timestamps
            if current_time - timestamp < self.time_window
        ]
        
        # Проверяем лимит
        if len(active_timestamps) >= self.max_requests:
            logger.warning(f"Rate limit превышен для пользователя {user_id}")
            # Обновляем данные пользователя и перемещаем в конец как активного
            user_requests[user_id] = active_timestamps
            user_requests.move_to_end(user_id)
            return False
        
        # Добавляем текущий запрос
        active_timestamps.append(current_time)
        user_requests[user_id] = active_timestamps
        # Перемещаем пользователя в конец OrderedDict (самый свежий)
        user_requests.move_to_end(user_id)
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
                    parse_mode=None
                )
            elif update.callback_query:
                await update.callback_query.answer(
                    f"⏳ Слишком много запросов. Подождите {self.time_window} секунд.",
                    show_alert=True
                )
            return
        
        # Передаем управление следующему обработчику
        return await next_handler(update, context)


# Глобальный экземпляр middleware
rate_limit_middleware = RateLimitMiddleware()
