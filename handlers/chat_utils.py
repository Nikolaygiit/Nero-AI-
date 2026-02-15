"""
Утилиты для обработки сообщений в чате
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
from services.image_gen import generate_with_queue, get_queue_position
try:
    from tasks.image_tasks import generate_image_task
    from tasks.broker import get_taskiq_queue_length
except ImportError:
    generate_image_task = None
    get_taskiq_queue_length = None
from utils.text_tools import sanitize_markdown
from utils.analytics import track
from utils.i18n import t
from services.rag import get_rag_context

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

IMAGE_KEYWORDS = ['картинк', 'изображен', 'создай', 'скинь', 'покажи', 'нарисуй', 'сгенерируй']

def is_image_request(user_message: str) -> bool:
    """Проверяет, является ли сообщение запросом на генерацию изображения"""
    return any(keyword in user_message.lower() for keyword in IMAGE_KEYWORDS)

def extract_image_prompt(user_message: str) -> str:
    """Извлекает промпт для генерации из сообщения"""
    prompt = user_message
    for keyword in IMAGE_KEYWORDS:
        prompt = prompt.replace(keyword, '').strip()
    if not prompt:
        prompt = "красивое изображение"
    return prompt

async def handle_image_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает запрос на генерацию изображения"""
    user_id = update.effective_user.id
    user_message = update.message.text

    prompt = extract_image_prompt(user_message)

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    await db.increment_daily_usage(user_id, date_str)
    track("generated_image", str(user_id), {"async": True})

    # Фоновая задача (Taskiq + Redis)
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

async def handle_multimodal_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Обрабатывает мультимодальные запросы (текст + предыдущее изображение).
    Возвращает True, если запрос был обработан."""
    user_id = update.effective_user.id
    user_message = update.message.text

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
            return True
        except Exception as e:
            logger.error("multimodal_response_error", user_id=user_id, error=str(e))
            context.user_data.pop('last_image_base64', None)
            return False
    return False

async def handle_text_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает стандартные текстовые запросы"""
    user_id = update.effective_user.id
    user_message = update.message.text

    # Очищаем контекст изображения, если он был
    context.user_data.pop('last_image_base64', None)

    # Сохраняем промпт для повтора
    context.user_data["last_prompt"] = user_message
    request_id = uuid.uuid4().hex[:8]
    if "prompts" not in context.user_data:
        context.user_data["prompts"] = {}
    context.user_data["prompts"][request_id] = user_message

    prompts_dict = context.user_data["prompts"]
    if len(prompts_dict) > 20:
        for k in list(prompts_dict.keys())[:-20]:
            del prompts_dict[k]

    await update.message.reply_chat_action("typing")

    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    await db.increment_daily_usage(user_id, date_str)
    track("sent_message", str(user_id), {"type": "text"})

    # RAG: подтянуть контекст
    rag_context = await get_rag_context(user_id, user_message)

    STREAM_EDIT_INTERVAL = 1.5
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

        def make_regenerate_keyboard(uid: int, req_id: str):
            return InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(t("btn_favorite"), callback_data=f"fav_{uid}"),
                    InlineKeyboardButton(t("btn_regenerate"), callback_data=f"retry_{uid}_{req_id}"),
                ],
                [InlineKeyboardButton(t("btn_rephrase"), callback_data=f"rephrase_{uid}")],
            ])

        if len(response) > 4096:
            parts = []
            current_part = ""
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

            for i, part in enumerate(parts):
                reply_markup = make_regenerate_keyboard(user_id, request_id) if i == len(parts) - 1 else None
                safe_part = sanitize_markdown(part)
                try:
                    await update.message.reply_text(safe_part, parse_mode='Markdown', reply_markup=reply_markup)
                except BadRequest as e:
                    if "parse" in str(e).lower() or "entities" in str(e).lower():
                        await update.message.reply_text(part, parse_mode=None, reply_markup=reply_markup)
                    else:
                        raise
        else:
            reply_markup = make_regenerate_keyboard(user_id, request_id)
            safe_response = sanitize_markdown(response)
            try:
                await update.message.reply_text(safe_response, parse_mode='Markdown', reply_markup=reply_markup)
            except BadRequest as e:
                if "parse" in str(e).lower() or "entities" in str(e).lower():
                    await update.message.reply_text(response, parse_mode=None, reply_markup=reply_markup)
                else:
                    raise

    except Exception as e:
        logger.error("message_processing_error", user_id=user_id, error=str(e))
        await update.message.reply_text(t("error_generic") + f": {str(e)[:200]}", parse_mode=None)
