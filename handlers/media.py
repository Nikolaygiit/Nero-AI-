"""
Обработчики медиа (фото, голос) — Vision + Whisper
"""
import logging
import base64
from utils.text_tools import sanitize_markdown
from utils.analytics import track
from io import BytesIO
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from services.gemini import gemini_service
from services.speech import speech_to_text
from middlewares.rate_limit import rate_limit_middleware
from middlewares.usage_limit import check_can_make_request

logger = logging.getLogger(__name__)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка загруженных фотографий"""
    user_id = update.effective_user.id
    
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {rate_limit_middleware.time_window} сек.",
            parse_mode=None
        )
        return
    can_proceed, limit_msg = await check_can_make_request(user_id)
    if not can_proceed:
        await update.message.reply_text(limit_msg, parse_mode=None)
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    
    caption = update.message.caption or "Опиши это изображение подробно на русском языке"
    
    # Проверяем, хочет ли пользователь генерацию изображения на основе фото
    generation_keywords = ['создай', 'сгенерируй', 'нарисуй', 'сделай', 'портрет', 'аватар', 'измени', 'замени']
    wants_generation = any(keyword in caption.lower() for keyword in generation_keywords)
    
    if wants_generation:
        # TODO: Реализовать генерацию изображения на основе фото
        await update.message.reply_text("⚠️ Генерация изображений на основе фото пока не реализована")
        return
    
    # Обычный анализ изображения
    analysis_msg = await update.message.reply_text("📸 Анализирую изображение...")
    
    try:
        # Скачиваем изображение
        photo_bytes = await file.download_as_bytearray()
        
        # Конвертируем в base64
        image_base64 = base64.b64encode(photo_bytes).decode('utf-8')

        # Сохраняем в контексте для мультимодального диалога (вопросы о картинке в чате)
        if context.user_data is not None:
            context.user_data['last_image_base64'] = image_base64
        
        # Анализируем через Gemini Vision
        analysis = await gemini_service.analyze_image(
            image_base64=image_base64,
            prompt=caption,
            user_id=user_id
        )
        
        track("analyzed_image", str(user_id))
        safe_analysis = sanitize_markdown(analysis)
        await analysis_msg.edit_text(f"📸 **Анализ изображения:**\n\n{safe_analysis}", parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка анализа изображения: {e}")
        await analysis_msg.edit_text(f"❌ Ошибка анализа изображения: {str(e)[:200]}")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка голосовых сообщений — Whisper STT, затем обработка как текст"""
    user_id = update.effective_user.id
    voice = update.message.voice
    if not voice:
        return

    can_proceed, limit_msg = await check_can_make_request(user_id)
    if not can_proceed:
        await update.message.reply_text(limit_msg, parse_mode=None)
        return

    processing_msg = await update.message.reply_text("🎤 Распознаю речь...")
    try:
        file = await context.bot.get_file(voice.file_id)
        voice_bytes = await file.download_as_bytearray()
        text = await speech_to_text(bytes(voice_bytes))
        if not text:
            await processing_msg.edit_text(
                "⚠️ Не удалось распознать речь.\n💡 Проверьте качество записи или напишите текстом."
            )
            return
        await processing_msg.delete()
        track("voice_transcribed", str(user_id))
        # Подставляем распознанный текст как новое сообщение — перенаправляем в handle_message
        from handlers.chat import handle_message
        update.message.text = text
        await handle_message(update, context)
    except Exception as e:
        logger.error("Ошибка голосового: %s", e)
        await processing_msg.edit_text(f"❌ Ошибка: {str(e)[:200]}")
