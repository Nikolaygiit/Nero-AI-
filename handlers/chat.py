"""
Обработчик текстовых сообщений
"""
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from services.gemini import gemini_service
from services.image_gen import image_generator, generate_with_queue, get_queue_position
from middlewares.rate_limit import rate_limit_middleware
from utils.text_tools import sanitize_markdown
import config

logger = logging.getLogger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    user_message = update.message.text
    
    # Проверка rate limit
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {rate_limit_middleware.time_window} секунд.\n\n"
            f"💡 Лимит: {rate_limit_middleware.max_requests} запросов в минуту",
            parse_mode=None
        )
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
        
        await update.message.reply_chat_action("upload_photo")
        position = await get_queue_position()
        status_text = "🎨 Генерирую изображение..."
        if position > 1:
            status_text = f"⏳ Вы {position}-й в очереди, ожидайте..."
        status_msg = await update.message.reply_text(status_text)
        
        try:
            image_bytes, strategy_name = await generate_with_queue(prompt, user_id)
            
            # Отправляем изображение
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
            except:
                pass
                
        except Exception as e:
            logger.error(f"Ошибка генерации изображения: {e}")
            await status_msg.edit_text(f"❌ Ошибка генерации изображения: {str(e)[:200]}")
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
    await update.message.reply_chat_action("typing")

    try:
        status_msg = await update.message.reply_text("⏳ Думаю...")
        accumulated = ""
        try:
            async for chunk in gemini_service.generate_content_stream(
                prompt=user_message,
                user_id=user_id,
                use_context=True
            ):
                accumulated += chunk
                if len(accumulated) > 100 and len(accumulated) % 200 < len(chunk):
                    try:
                        safe = sanitize_markdown(accumulated)
                        await status_msg.edit_text(safe, parse_mode='Markdown')
                    except Exception:
                        pass
            response = accumulated
        except Exception as stream_err:
            logger.warning(f"Stream error, fallback: {stream_err}")
            response = await gemini_service.generate_content(
                prompt=user_message, user_id=user_id, use_context=True
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
                            InlineKeyboardButton("⭐ В избранное", callback_data=f"fav_{user_id}"),
                            InlineKeyboardButton("🔄 Перефразировать", callback_data=f"rephrase_{user_id}")
                        ]
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
                    InlineKeyboardButton("⭐ В избранное", callback_data=f"fav_{user_id}"),
                    InlineKeyboardButton("🔄 Перефразировать", callback_data=f"rephrase_{user_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            safe_response = sanitize_markdown(response)
            await update.message.reply_text(safe_response, parse_mode='Markdown', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        error_text = f"❌ Произошла ошибка при обработке запроса: {str(e)[:200]}"
        await update.message.reply_text(error_text, parse_mode=None)
