"""
RAG Lite — долгосрочная память: факты о пользователе в контексте
Сохраняем важные факты, подмешиваем в промпт при генерации
"""
import logging
import re
from typing import List, Optional

from database import db

logger = logging.getLogger(__name__)

# Паттерны для извлечения фактов (имя, профессия и т.д.)
FACT_PATTERNS = [
    (r"(?:меня зовут|мое имя|я\s+)?([А-Яа-яA-Za-z]{2,20})\s*(?:\.|,|$)", "name"),
    (r"мне\s+(\d{1,3})\s*(?:лет|год)", "age"),
    (r"я\s+(?:работаю|работал)\s+(?:как\s+)?([^\.]+)", "job"),
    (r"живу в ([^\.]+)", "city"),
    (r"я\s+([а-яё]+(?:олог|ист|ер|ор|ант))", "profession"),
]


async def extract_and_save_facts(user_id: int, user_message: str) -> None:
    """
    Извлекает факты из сообщения пользователя и сохраняет в БД.
    """
    msg_lower = user_message.lower().strip()
    if len(msg_lower) < 10:
        return
    for pattern, fact_type in FACT_PATTERNS:
        m = re.search(pattern, user_message, re.IGNORECASE)
        if m:
            value = m.group(1).strip()[:200]
            if len(value) > 2:
                try:
                    await db.add_user_fact(user_id, fact_type, value)
                except Exception as e:
                    logger.debug("Fact save skip: %s", e)


async def get_relevant_facts(user_id: int, limit: int = 5) -> str:
    """
    Возвращает строку с фактами для добавления в системный промпт.
    """
    facts = await db.get_user_facts(user_id, limit=limit)
    if not facts:
        return ""
    lines = ["Известные факты о пользователе:"]
    for f in facts:
        lines.append(f"- {f.fact_type}: {f.fact_value}")
    return "\n".join(lines)
