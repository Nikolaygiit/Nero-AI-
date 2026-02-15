"""
Обработчик текстовых сообщений
"""
import structlog
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from middlewares.rate_limit import rate_limit_middleware
from middlewares.usage_limit import check_can_make_request
from utils.i18n import t
from services.memory import extract_and_save_facts
from handlers.chat_utils import (
    is_image_request,
    handle_image_request,
    handle_multimodal_request,
    handle_text_request
)

logger = structlog.get_logger(__name__)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    if await db.is_banned(user_id):
        await update.message.reply_text("⛔ Вы заблокированы и не можете использовать бота.")
        return
    user_message = update.message.text
    logger.info("message_received", user_id=user_id, text_len=len(user_message))

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
    if is_image_request(user_message):
        await handle_image_request(update, context)
        return
    
    # Мультимодальный контекст
    if await handle_multimodal_request(update, context):
        return

    # Обычная обработка текста
    await handle_text_request(update, context)
