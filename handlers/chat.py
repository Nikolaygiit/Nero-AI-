"""
Обработчик текстовых сообщений
"""
import re
import time
import uuid
import structlog
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from database import db
from services.gemini import gemini_service
from services.image_gen import image_generator, generate_with_queue, get_queue_position

try:
    from tasks.image_tasks import generate_image_task
    from tasks.broker import get_taskiq_queue_length
except ImportError:
    generate_image_task = None
    get_taskiq_queue_length = None
from middlewares.rate_limit import rate_limit_middleware
from middlewares.usage_limit import check_can_make_request
from utils.text_tools import sanitize_markdown
from utils.analytics import track
from utils.i18n import t
from services.memory import extract_and_save_facts
from services.rag import get_rag_context
from handlers.chat_utils import make_regenerate_keyboard, split_long_message
import config

logger = structlog.get_logger(__name__)


async def generate_and_reply_text(chat, user_id: int, prompt: str, context, rag_context: str = None) -> str:
    """Генерация ответа (стриминг) — возвращает полный текст. Используется в handle_message и retry."""
    accumulated = ""
    try:
        async for chunk in gemini_service.generate_content_stream(
            prompt=prompt, user_id=user_id, use_context=True, rag_context=rag_context
        ):
            accumulated += chunk
    except Exception:
        accumulated = await gemini_service.generate_content(
            prompt=prompt, user_id=user_id, use_context=True, rag_context=rag_context
        )
    return accumulated


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

        # Фоновая задача (Taskiq + Redis): бот сразу отвечает с позицией в очереди, воркер шлёт результат позже
        if generate_image_task is not None and get_taskiq_queue_length is not None:
            try:
                queue_len = await get_taskiq_queue_length()
                await generate_image_task.kiq(
                    prompt=prompt,
                    chat_id=update.effective_chat.id,
                    user_id=user_id,
                )
                position = queue_len + 1
                if position > 1:
                    await update.message.reply_text(t("image_taken_queue", position=position), parse_mode=None)
                else:
                    await update.message.reply_text(t("image_taken"), parse_mode=None)
                return
            except Exception as e:
                logger.warning("taskiq_unavailable", error=str(e), fallback="sync_generation")

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
            logger.error("image_generation_error", user_id=user_id, error=str(e))
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
            logger.error("multimodal_response_error", user_id=user_id, error=str(e))
            context.user_data.pop('last_image_base64', None)

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

    STREAM_EDIT_INTERVAL = 1.5  # обновлять сообщение не чаще раз в 1.5 сек (защита от лимитов Telegram)
    try:
        status_msg = await update.message.reply_text(t("thinking"))
        accumulated = ""
        last_edit_at = 0.0
        try:
            async for chunk in gemini_service.generate_content_stream(
                prompt=user_message,
                user_id=user_id,
                use_context=True,
                rag_context=rag_context,
            ):
                accumulated += chunk
                now = time.monotonic()
                # Обновляем сообщение раз в 1–2 сек, чтобы не спамить API и выглядело как стриминг
                if len(accumulated) > 50 and (now - last_edit_at >= STREAM_EDIT_INTERVAL):
                    try:
                        safe = sanitize_markdown(accumulated)
                        await status_msg.edit_text(safe, parse_mode="Markdown")
                        last_edit_at = now
                    except BadRequest as e:
                        if "parse" in str(e).lower() or "entities" in str(e).lower():
                            try:
                                await status_msg.edit_text(accumulated, parse_mode=None)
                            except Exception:
                                pass
                        last_edit_at = now
                    except Exception:
                        pass
            response = accumulated
            # Финальное обновление: если не успели обновить в последнем интервале — показываем полный текст
            if response and (time.monotonic() - last_edit_at >= STREAM_EDIT_INTERVAL or last_edit_at == 0):
                try:
                    safe = sanitize_markdown(response)
                    await status_msg.edit_text(safe, parse_mode="Markdown")
                except BadRequest as e:
                    if "parse" in str(e).lower() or "entities" in str(e).lower():
                        try:
                            await status_msg.edit_text(response, parse_mode=None)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as stream_err:
            logger.warning("stream_error", user_id=user_id, error=str(stream_err), fallback="non_stream")
            response = await generate_and_reply_text(
                update.effective_chat, user_id, user_message, context, rag_context=rag_context
            )
        try:
            await status_msg.delete()
        except Exception:
            pass

        # Разбиваем длинные сообщения на части (лимит Telegram - 4096 символов)
        parts = split_long_message(response, max_length=4000)

        for i, part in enumerate(parts):
            # Клавиатуру добавляем только к последней части
            is_last = (i == len(parts) - 1)
            reply_markup = make_regenerate_keyboard(user_id, request_id) if is_last else None

            safe_part = sanitize_markdown(part)
            try:
                await update.message.reply_text(safe_part, parse_mode='Markdown', reply_markup=reply_markup)
            except BadRequest as e:
                # Если markdown сломался (например, из-за разбиения посередине жирного текста), шлём без него
                if "parse" in str(e).lower() or "entities" in str(e).lower():
                    await update.message.reply_text(part, parse_mode=None, reply_markup=reply_markup)
                else:
                    raise
            
    except Exception as e:
        logger.error("message_processing_error", user_id=user_id, error=str(e))
        await update.message.reply_text(t("error_generic") + f": {str(e)[:200]}", parse_mode=None)
