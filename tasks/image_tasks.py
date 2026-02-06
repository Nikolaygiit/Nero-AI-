"""
Фоновая генерация изображений — бот отвечает "Взял в работу", результат приходит позже
"""
import logging
from io import BytesIO

from telegram import Bot

import config
from services.image_gen import image_generator

from .broker import broker

logger = logging.getLogger(__name__)

if broker:

    @broker.task
    async def generate_image_task(
        prompt: str,
        chat_id: int,
        user_id: int,
    ) -> None:
        """Фоновая задача: генерирует изображение и отправляет пользователю."""
        try:
            image_bytes, strategy = await image_generator.generate(prompt, user_id)
            bot = Bot(token=config.settings.TELEGRAM_BOT_TOKEN)
            photo = BytesIO(image_bytes)
            photo.name = "image.png"
            caption = f"✨ Изображение готово!\n\n📝 Описание: {prompt}\n💡 Использовано: {strategy}"
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
            )
            logger.info("Image task done for chat_id=%s", chat_id)
        except Exception as e:
            logger.error("Image task failed: %s", e, exc_info=True)
            try:
                err_bot = Bot(token=config.settings.TELEGRAM_BOT_TOKEN)
                await err_bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Ошибка генерации изображения: {str(e)[:200]}",
                )
            except Exception:
                pass
else:
    generate_image_task = None  # type: ignore
