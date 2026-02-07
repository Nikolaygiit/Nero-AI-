"""
Проверка бана пользователя перед обработкой запросов
"""
from database import db


async def is_user_banned(user_id: int) -> bool:
    """Проверить, забанен ли пользователь"""
    return await db.is_banned(user_id)
