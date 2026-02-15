"""
Скрипт миграции данных из JSON в SQLite
"""
import asyncio
import json
import logging
import os

from database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_from_json(json_file: str = 'bot_data.json'):
    """Миграция данных из JSON файла в SQLite"""

    # Инициализация базы данных
    await db.init()

    if not json_file or not os.path.exists(json_file):
        logger.warning(f"Файл {json_file} не найден. Миграция пропущена.")
        return

    logger.info(f"Начинаю миграцию данных из {json_file}...")

    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Миграция пользователей и настроек
        settings = data.get('settings', {})
        for user_id_str, user_settings in settings.items():
            try:
                user_id = int(user_id_str)
                await db.create_or_update_user(
                    telegram_id=user_id,
                    language=user_settings.get('language', 'ru'),
                    persona=user_settings.get('persona', 'assistant'),
                    model=user_settings.get('model', 'auto'),
                    image_model=user_settings.get('image_model', 'auto')
                )
            except Exception as e:
                logger.error(f"Ошибка миграции пользователя {user_id_str}: {e}")

        logger.info(f"Мигрировано {len(settings)} пользователей")

        # Миграция истории сообщений
        conversations = data.get('conversations', {})
        migrated_messages = 0
        for user_id_str, messages in conversations.items():
            try:
                user_id = int(user_id_str)
                for msg in messages[-20:]:  # Берем последние 20 сообщений
                    await db.add_message(
                        user_id=user_id,
                        role=msg.get('role', 'user'),
                        content=msg.get('content', '')
                    )
                    migrated_messages += 1
            except Exception as e:
                logger.error(f"Ошибка миграции сообщений пользователя {user_id_str}: {e}")

        logger.info(f"Мигрировано {migrated_messages} сообщений")

        # Миграция статистики
        stats_data = data.get('stats', {})
        for user_id_str, stats in stats_data.items():
            try:
                user_id = int(user_id_str)
                commands_used = stats.get('commands_used', {})
                if isinstance(commands_used, dict):
                    for command, count in commands_used.items():
                        for _ in range(count):
                            await db.update_stats(user_id, command=command)

                await db.update_stats(
                    user_id,
                    requests_count=stats.get('requests', 0),
                    tokens_used=stats.get('tokens_used', 0),
                    images_generated=stats.get('images_generated', 0)
                )
            except Exception as e:
                logger.error(f"Ошибка миграции статистики пользователя {user_id_str}: {e}")

        logger.info(f"Мигрировано статистики для {len(stats_data)} пользователей")

        # Миграция избранного
        favorites = data.get('favorites', {})
        migrated_favorites = 0
        for user_id_str, fav_list in favorites.items():
            try:
                user_id = int(user_id_str)
                for fav in fav_list:
                    await db.add_favorite(
                        user_id=user_id,
                        content=fav.get('content', ''),
                        content_type=fav.get('type', 'text'),
                        tags=fav.get('tags', [])
                    )
                    migrated_favorites += 1
            except Exception as e:
                logger.error(f"Ошибка миграции избранного пользователя {user_id_str}: {e}")

        logger.info(f"Мигрировано {migrated_favorites} записей избранного")

        # Миграция достижений
        achievements = data.get('achievements', {})
        migrated_achievements = 0
        for user_id_str, ach_list in achievements.items():
            try:
                user_id = int(user_id_str)
                for ach_id in ach_list:
                    await db.add_achievement(user_id, ach_id)
                    migrated_achievements += 1
            except Exception as e:
                logger.error(f"Ошибка миграции достижений пользователя {user_id_str}: {e}")

        logger.info(f"Мигрировано {migrated_achievements} достижений")

        logger.info("✅ Миграция завершена успешно!")

    except Exception as e:
        logger.error(f"Ошибка миграции: {e}", exc_info=True)
    finally:
        await db.close()


if __name__ == '__main__':
    asyncio.run(migrate_from_json())
