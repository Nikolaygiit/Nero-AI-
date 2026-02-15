import re
import time
from datetime import datetime

import structlog
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from database import db
from services.gemini import gemini_service
from services.image_gen import generate_with_queue, get_queue_position
from utils.analytics import track
from utils.i18n import t
from utils.text_tools import sanitize_markdown

try:
    from tasks.broker import get_taskiq_queue_length
    from tasks.image_tasks import generate_image_task
except ImportError:
    generate_image_task = None
    get_taskiq_queue_length = None

logger = structlog.get_logger(__name__)

IMAGE_KEYWORDS = ['картинк', 'изображен', 'создай', 'скинь', 'покажи', 'нарисуй', 'сгенерируй']

def is_image_request(text: str) -> bool:
    """Проверяет, является ли сообщение запросом на генерацию изображения."""
    return any(keyword in text.lower() for keyword in IMAGE_KEYWORDS)

def get_image_prompt(text: str) -> str:
    """Извлекает промпт для изображения из текста."""
    prompt = text
    # Сортируем ключевые слова по длине, чтобы сначала удалять самые длинные (например "сгенерируй изображение")
    sorted_keywords = sorted(IMAGE_KEYWORDS, key=len, reverse=True)
    for keyword in sorted_keywords:
        # Используем regex с границами слова, чтобы не удалять части слов
        # Но для русского языка \b работает не всегда корректно с кириллицей, поэтому просто заменяем
        if keyword in prompt.lower():
            pattern = re.compile(re.escape(keyword), re.IGNORECASE)
            prompt = pattern.sub('', prompt, count=1).strip()

    # Удаляем лишние пробелы и знаки препинания в начале. Также удаляем "у" в начале, если оно осталось от "картинку"
    prompt = re.sub(r'^[\s,.]+', '', prompt).strip()
    if prompt.lower().startswith('у '):
        prompt = prompt[2:].strip()

    return prompt if prompt else "красивое изображение"

async def handle_image_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, user_id: int):
    """Обрабатывает запрос на генерацию изображения."""
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
            msg_key = "image_taken_queue" if position > 1 else "image_taken"
            await update.message.reply_text(t(msg_key, position=position), parse_mode=None)
            return
        except Exception as e:
            logger.warning("taskiq_unavailable", error=str(e), fallback="sync_generation")

    # Fallback: синхронная генерация
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

async def handle_multimodal_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message: str, user_id: int) -> bool:
    """
    Обрабатывает запрос с контекстом изображения (если есть).
    Возвращает True, если запрос обработан, иначе False.
    """
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
            # Удаляем картинку из контекста после использования (одноразовый контекст для простоты)
            context.user_data.pop('last_image_base64', None)
            safe_response = sanitize_markdown(response)
            await update.message.reply_text(safe_response, parse_mode='Markdown')
            return True
        except Exception as e:
            logger.error("multimodal_response_error", user_id=user_id, error=str(e))
            context.user_data.pop('last_image_base64', None)

    # Если не обработали как мультимодальный, но картинка была - очищаем
    if context.user_data:
        context.user_data.pop('last_image_base64', None)

    return False

async def generate_and_reply_text(chat, user_id: int, prompt: str, context, rag_context: str = None) -> str:
    """Генерация ответа (стриминг) — возвращает полный текст. Используется при ошибке стриминга и для retry."""
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

async def stream_text_response(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message: str, user_id: int, rag_context: str = None):
    """
    Основная логика потоковой генерации ответа.
    """
    stream_edit_interval = 1.5
    status_msg = await update.message.reply_text(t("thinking"))
    accumulated = ""
    last_edit_at = 0.0
    response = ""

    try:
        try:
            async for chunk in gemini_service.generate_content_stream(
                prompt=user_message,
                user_id=user_id,
                use_context=True,
                rag_context=rag_context,
            ):
                accumulated += chunk
                now = time.monotonic()
                if len(accumulated) > 50 and (now - last_edit_at >= stream_edit_interval):
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
            # Финальное обновление
            if response and (time.monotonic() - last_edit_at >= stream_edit_interval or last_edit_at == 0):
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

        return response

    except Exception as e:
        logger.error("stream_response_error", user_id=user_id, error=str(e))
        await update.message.reply_text(t("error_generic") + f": {str(e)[:200]}", parse_mode=None)
        return None

def make_regenerate_keyboard(uid: int, req_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками регенерации."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("btn_favorite"), callback_data=f"fav_{uid}"),
            InlineKeyboardButton(t("btn_regenerate"), callback_data=f"retry_{uid}_{req_id}"),
        ],
        [InlineKeyboardButton(t("btn_rephrase"), callback_data=f"rephrase_{uid}")],
    ])

async def send_response_parts(update: Update, response: str, user_id: int, request_id: str):
    """Отправляет ответ частями, если он слишком длинный."""
    if not response:
        return

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
