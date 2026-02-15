"""
RAG Lite — долгосрочная память: факты о пользователе в контексте
Сохраняем важные факты, подмешиваем в промпт при генерации
"""

import json
import re
from typing import Dict

import structlog

import config
from database import db
from services.gemini import gemini_service

logger = structlog.get_logger(__name__)

# Резервные паттерны для извлечения фактов (если Gemini недоступен)
FACT_PATTERNS = [
    (r"(?:меня зовут|мое имя|я\s+)?([А-Яа-яA-Za-z]{2,20})\s*(?:\.|,|$)", "name"),
    (r"мне\s+(\d{1,3})\s*(?:лет|год)", "age"),
    (r"я\s+(?:работаю|работал)\s+(?:как\s+)?([^\.]+)", "job"),
    (r"живу в ([^\.]+)", "city"),
    (r"я\s+([а-яё]+(?:олог|ист|ер|ор|ант))", "profession"),
]


async def extract_facts_with_gemini(user_message: str) -> Dict[str, str]:
    """
    Использует Gemini API для извлечения структурированных фактов из сообщения.
    Возвращает словарь {fact_type: fact_value} или пустой словарь при ошибке.
    """
    prompt = f"""Проанализируй сообщение пользователя и извлеки важные факты о нём.

Сообщение: "{user_message}"

Извлеки факты в формате JSON. Доступные типы фактов:
- name: имя пользователя
- age: возраст (только число)
- job: место работы или профессия
- city: город проживания
- profession: профессия (разработчик, дизайнер, учитель и т.д.)
- interests: интересы и хобби
- education: образование
- skills: навыки и умения

Верни ТОЛЬКО валидный JSON без дополнительного текста, например:
{{"name": "Николай", "profession": "Python-разработчик"}}

Если фактов нет, верни {{}}."""

    try:
        # Используем лёгкую модель (Gemini Flash) для быстрого извлечения фактов
        fact_model = (
            getattr(config.settings, "FACT_EXTRACTION_MODEL", "gemini-2.0-flash")
            or "gemini-2.0-flash"
        )
        response = await gemini_service.generate_content(
            prompt=prompt,
            user_id=None,  # без контекста пользователя
            use_context=False,
            model=fact_model,
        )

        # Очищаем ответ от markdown блоков кода, если есть
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        # Парсим JSON
        facts = json.loads(response)
        if isinstance(facts, dict):
            # Фильтруем пустые значения
            return {k: str(v).strip()[:200] for k, v in facts.items() if v and str(v).strip()}
        return {}
    except json.JSONDecodeError as e:
        logger.debug("fact_extraction_failed", error=str(e), method="gemini")
        return {}
    except Exception as e:
        logger.debug("fact_extraction_failed", error=str(e), method="gemini", fallback="regex")
        return {}


async def extract_and_save_facts(user_id: int, user_message: str) -> None:
    """
    Извлекает факты из сообщения пользователя через Gemini API и сохраняет в БД.
    При ошибке Gemini использует резервные regex-паттерны.
    """
    msg_lower = user_message.lower().strip()
    if len(msg_lower) < 10:
        return

    # Пробуем извлечь факты через Gemini
    facts = await extract_facts_with_gemini(user_message)

    # Если Gemini вернул факты — сохраняем их
    if facts:
        for fact_type, fact_value in facts.items():
            if len(fact_value) > 2:
                try:
                    await db.add_user_fact(user_id, fact_type, fact_value)
                    logger.debug(
                        "fact_saved",
                        user_id=user_id,
                        fact_type=fact_type,
                        fact_value=fact_value[:50],
                    )
                except Exception as e:
                    logger.debug("fact_save_skipped", user_id=user_id, error=str(e))
        return

    # Fallback: используем regex-паттерны
    for pattern, fact_type in FACT_PATTERNS:
        m = re.search(pattern, user_message, re.IGNORECASE)
        if m:
            value = m.group(1).strip()[:200]
            if len(value) > 2:
                try:
                    await db.add_user_fact(user_id, fact_type, value)
                    logger.debug(
                        "fact_saved",
                        user_id=user_id,
                        fact_type=fact_type,
                        fact_value=value[:50],
                        method="regex",
                    )
                except Exception as e:
                    logger.debug("fact_save_skipped", user_id=user_id, error=str(e))


async def get_relevant_facts(user_id: int, limit: int = 5) -> str:
    """
    Возвращает строку с фактами для добавления в системный промпт.
    Форматирует факты в читаемом виде для модели.
    """
    facts = await db.get_user_facts(user_id, limit=limit)
    if not facts:
        return ""

    # Группируем факты по типам для лучшей читаемости
    fact_dict = {}
    for f in facts:
        if f.fact_type not in fact_dict:
            fact_dict[f.fact_type] = []
        fact_dict[f.fact_type].append(f.fact_value)

    # Формируем читаемый текст
    lines = ["\nИзвестные факты о пользователе:"]

    type_names = {
        "name": "Имя",
        "age": "Возраст",
        "job": "Работа",
        "city": "Город",
        "profession": "Профессия",
        "interests": "Интересы",
        "education": "Образование",
        "skills": "Навыки",
    }

    for fact_type, values in fact_dict.items():
        type_name = type_names.get(fact_type, fact_type)
        value_str = ", ".join(values) if len(values) > 1 else values[0]
        lines.append(f"- {type_name}: {value_str}")

    return "\n".join(lines)
