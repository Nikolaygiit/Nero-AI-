"""
Обработчик текстовых сообщений
"""
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from services.gemini import gemini_service
from services.image_gen import image_generator
from middlewares.rate_limit import rate_limit_middleware
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
        status_msg = await update.message.reply_text("🎨 Генерирую изображение...")
        
        try:
            image_bytes, strategy_name = await image_generator.generate(prompt, user_id)
            
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
    
    # Обычная обработка текста
    await update.message.reply_chat_action("typing")
    
    try:
        # Генерируем ответ через Gemini
        response = await gemini_service.generate_content(
            prompt=user_message,
            user_id=user_id,
            use_context=True
        )
        
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
                    await update.message.reply_text(part, parse_mode='Markdown', reply_markup=reply_markup)
                else:
                    await update.message.reply_text(part, parse_mode='Markdown')
        else:
            # Обычное сообщение с кнопками
            keyboard = [
                [
                    InlineKeyboardButton("⭐ В избранное", callback_data=f"fav_{user_id}"),
                    InlineKeyboardButton("🔄 Перефразировать", callback_data=f"rephrase_{user_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(response, parse_mode='Markdown', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        error_text = f"❌ Произошла ошибка при обработке запроса: {str(e)[:200]}"
        await update.message.reply_text(error_text, parse_mode=None)
