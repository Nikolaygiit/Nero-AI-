"""
Обработчик текстовых сообщений
"""
import uuid
from datetime import datetime

import structlog
from telegram import Update
from telegram.ext import ContextTypes

from database import db
from handlers.chat_utils import (
    get_image_prompt,
    handle_image_generation,
    handle_multimodal_request,
    is_image_request,
    send_response_parts,
    stream_text_response,
)
from middlewares.rate_limit import rate_limit_middleware
from middlewares.usage_limit import check_can_make_request
from services.memory import extract_and_save_facts
from services.rag import get_rag_context
from utils.analytics import track
from utils.i18n import t

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
        prompt = get_image_prompt(user_message)
        await handle_image_generation(update, context, prompt, user_id)
        return

    # Мультимодальный контекст: вопрос о ранее отправленном изображении
    if await handle_multimodal_request(update, context, user_message, user_id):
        return

    # Обычная обработка текста (потоковая генерация)
    context.user_data.pop('last_image_base64', None)
    context.user_data["last_prompt"] = user_message

    # ID запроса для кнопки «Перегенерировать» — в callback_data передаём его, чтобы знать, какой промпт перезапускать
    request_id = uuid.uuid4().hex[:8]
    if "prompts" not in context.user_data:
        context.user_data["prompts"] = {}
    context.user_data["prompts"][request_id] = user_message

    # Храним только последние 20 запросов, чтобы не раздувать память
    prompts_dict = context.user_data["prompts"]
    if len(prompts_dict) > 20:
        for k in list(prompts_dict.keys())[:-20]:
            del prompts_dict[k]

    await update.message.reply_chat_action("typing")

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    await db.increment_daily_usage(user_id, date_str)
    track("sent_message", str(user_id), {"type": "text"})

    # RAG: подтянуть контекст из загруженных PDF (если есть документы и запрос похож на вопрос)
    rag_context = await get_rag_context(user_id, user_message)

    # Генерация и отправка ответа
    response = await stream_text_response(update, context, user_message, user_id, rag_context)

    if response:
        await send_response_parts(update, response, user_id, request_id)
