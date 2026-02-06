"""
Обработчик текстовых сообщений
"""
import logging
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from services.gemini import gemini_service
from services.image_gen import image_generator, generate_with_queue, get_queue_position

try:
    from tasks.image_tasks import generate_image_task
except ImportError:
    generate_image_task = None
from middlewares.rate_limit import rate_limit_middleware
from middlewares.usage_limit import check_can_make_request
from utils.text_tools import sanitize_markdown
from utils.analytics import track
from utils.i18n import t
from services.memory import extract_and_save_facts
import config

logger = logging.getLogger(__name__)


async def generate_and_reply_text(chat, user_id: int, prompt: str, context) -> str:
    """Генерация ответа (стриминг) — возвращает полный текст. Используется в handle_message и retry."""
    accumulated = ""
    try:
        async for chunk in gemini_service.generate_content_stream(
            prompt=prompt, user_id=user_id, use_context=True
        ):
            accumulated += chunk
    except Exception:
        accumulated = await gemini_service.generate_content(
            prompt=prompt, user_id=user_id, use_context=True
        )
    return accumulated


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # RAG Lite: извлекаем факты из сообщения
    await extract_and_save_facts(user_id, user_message)

    # Проверка rate limit
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            t("rate_limit") + f" {rate_limit_middleware.time_window} сек.\n💡 Лимит: {rate_limit_middleware.max_requests} запросов в минуту",
            parse_mode=None
        )
        return

    # Лимит бесплатных запросов (10/день)
    can_proceed, limit_msg = await check_can_make_request(user_id)
    if not can_proceed:
        await update.message.reply_text(limit_msg, parse_mode=None)
        return
    
    # Проверка на запрос изображения
    image_keywords = ['картинк', 'изображен', 'создай', 'скинь', 'покажи', 'нарисуй', 'сгенерируй']
    wants_image = any(keyword in user_message.lower() for keyword in image_keywords)
    
    if wants_image:
        # Генерация изображения
        prompt = user_message
        for keyword in image_keywords:
            prompt = prompt.replace(keyword, '').strip()
        if not prompt:
            prompt = "красивое изображение"

        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        await db.increment_daily_usage(user_id, date_str)
        track("generated_image", str(user_id), {"async": True})

        # Фоновая задача (Taskiq + Redis): бот отвечает "Взял в работу", результат приходит позже
        if generate_image_task is not None:
            try:
                await generate_image_task.kiq(
                    prompt=prompt,
                    chat_id=update.effective_chat.id,
                    user_id=user_id,
                )
                await update.message.reply_text(t("image_taken"), parse_mode=None)
                return
            except Exception as e:
                logger.warning("Taskiq недоступен, fallback на синхронную генерацию: %s", e)

        # Fallback: синхронная генерация (без Redis)
        await update.message.reply_chat_action("upload_photo")
        position = await get_queue_position()
        status_text = "🎨 Генерирую изображение..."
        if position > 1:
            status_text = f"⏳ Вы {position}-й в очереди, ожидайте..."
        status_msg = await update.message.reply_text(status_text)

        try:
            image_bytes, strategy_name = await generate_with_queue(prompt, user_id)

            from io import BytesIO
            photo_file = BytesIO(image_bytes)
            photo_file.name = "image.png"

            caption = f"✨ Изображение готово!\n\n📝 Описание: {prompt}\n💡 Использовано: {strategy_name}"

            await update.message.reply_photo(
                photo=photo_file,
                caption=caption,
                parse_mode=None
            )

            try:
                await status_msg.delete()
            except Exception:
                pass

        except Exception as e:
            logger.error("Ошибка генерации изображения: %s", e)
            await status_msg.edit_text(t("error_image") + f": {str(e)[:200]}")
        return
    
    # Мультимодальный контекст: вопрос о ранее отправленном изображении
    last_image = context.user_data.get('last_image_base64') if context.user_data else None
    if last_image and len(user_message) > 5:
        await update.message.reply_chat_action("typing")
        try:
            response = await gemini_service.generate_with_image_context(
                prompt=user_message,
                image_base64=last_image,
                user_id=user_id,
                use_context=True
            )
            context.user_data.pop('last_image_base64', None)
            safe_response = sanitize_markdown(response)
            await update.message.reply_text(safe_response, parse_mode='Markdown')
            return
        except Exception as e:
            logger.error(f"Ошибка мультимодального ответа: {e}")
            context.user_data.pop('last_image_base64', None)

    # Обычная обработка текста (потоковая генерация)
    context.user_data.pop('last_image_base64', None)
        context.user_data["last_prompt"] = user_message
    await update.message.reply_chat_action("typing")

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    await db.increment_daily_usage(user_id, date_str)
    track("sent_message", str(user_id), {"type": "text"})

    try:
        status_msg = await update.message.reply_text(t("thinking"))
        accumulated = ""
        try:
            async for chunk in gemini_service.generate_content_stream(
                prompt=user_message,
                user_id=user_id,
                use_context=True
            ):
                accumulated += chunk
                if len(accumulated) > 50 and len(accumulated) % 80 < len(chunk):
                    try:
                        safe = sanitize_markdown(accumulated)
                        await status_msg.edit_text(safe, parse_mode="Markdown")
                    except Exception:
                        pass
            response = accumulated
        except Exception as stream_err:
            logger.warning("Stream error, fallback: %s", stream_err)
            response = await generate_and_reply_text(
                update.effective_chat, user_id, user_message, context
            )
        try:
            await status_msg.delete()
        except Exception:
            pass

        # Разбиваем длинные сообщения на части (лимит Telegram - 4096 символов)
        if len(response) > 4096:
            # Разбиваем по абзацам
            parts = []
            current_part = ""
            
            # Пробуем разбить по блокам кода
            code_blocks = re.split(r'(```[\s\S]*?```)', response)
            
            for block in code_blocks:
                if len(current_part) + len(block) > 4000:
                    if current_part:
                        parts.append(current_part)
                    current_part = block
                else:
                    current_part += block
            
            if current_part:
                parts.append(current_part)
            
            # Отправляем части
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # Последняя часть с кнопками
                    keyboard = [
                        [
                            InlineKeyboardButton(t("btn_favorite"), callback_data=f"fav_{user_id}"),
                            InlineKeyboardButton(t("btn_regenerate"), callback_data=f"retry_{user_id}"),
                        ],
                        [InlineKeyboardButton(t("btn_rephrase"), callback_data=f"rephrase_{user_id}")],
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    safe_part = sanitize_markdown(part)
                    await update.message.reply_text(safe_part, parse_mode='Markdown', reply_markup=reply_markup)
                else:
                    safe_part = sanitize_markdown(part)
                    await update.message.reply_text(safe_part, parse_mode='Markdown')
        else:
            # Обычное сообщение с кнопками
            keyboard = [
                [
                    InlineKeyboardButton(t("btn_favorite"), callback_data=f"fav_{user_id}"),
                    InlineKeyboardButton(t("btn_regenerate"), callback_data=f"retry_{user_id}"),
                ],
                [InlineKeyboardButton(t("btn_rephrase"), callback_data=f"rephrase_{user_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            safe_response = sanitize_markdown(response)
            await update.message.reply_text(safe_response, parse_mode='Markdown', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error("Ошибка обработки сообщения: %s", e)
        await update.message.reply_text(t("error_generic") + f": {str(e)[:200]}", parse_mode=None)
