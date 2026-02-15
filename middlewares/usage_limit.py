"""
Лимит бесплатных запросов: 10/день, премиум — без лимита
"""

from datetime import datetime

import config
from database import db


async def check_can_make_request(user_id: int) -> tuple[bool, str]:
    """
    Проверка: может ли пользователь сделать запрос.
    Returns: (can_proceed, message)
    """
    is_premium = await db.is_premium(user_id)
    if is_premium:
        return True, ""

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    used = await db.get_daily_usage(user_id, date_str)
    limit = config.FREE_DAILY_LIMIT
    if used >= limit:
        return False, (
            f"⏳ Достигнут дневной лимит ({limit} запросов).\n\n💎 Оформите подписку для безлимитного доступа."
        )
    return True, ""
