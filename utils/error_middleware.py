"""
Централизованная обработка ошибок:
- Логирование в файл с трейсбеком
- Вежливое сообщение пользователю
- Отправка трейсбека админу
- Повторные попытки при сетевых ошибках (NetworkError, ConnectError)
"""

import asyncio
import logging
import traceback
from functools import wraps

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import ContextTypes

import config

logger = logging.getLogger(__name__)

# Сообщение пользователю при любой ошибке в хендлере
USER_MESSAGE = "Произошла ошибка, разработчики уже знают."
ADMIN_MESSAGE_PREFIX = "🐛 **Ошибка бота:**\n\n"

# Сетевые ошибки, при которых имеет смысл повторить запрос.
# telegram при httpx.RemoteProtocolError / ConnectError выбрасывает telegram.error.NetworkError
RETRYABLE_ERRORS: tuple = (NetworkError, ConnectionError, OSError)
try:
    import httpx

    RETRYABLE_ERRORS = (
        NetworkError,
        ConnectionError,
        OSError,
        httpx.RemoteProtocolError,
        httpx.ConnectError,
        httpx.ReadTimeout,
    )
except Exception:
    pass


async def send_message_with_retry(
    bot, chat_id: int, text: str, parse_mode: str = None, max_attempts: int = 3
):
    """
    Отправляет сообщение в Telegram с повторными попытками при сетевых ошибках.
    Уменьшает спам админу из-за NetworkError / RemoteProtocolError / ConnectError.
    """
    last_err = None
    for attempt in range(max_attempts):
        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            return
        except RETRYABLE_ERRORS as e:
            last_err = e
            if attempt < max_attempts - 1:
                wait_sec = 1.5**attempt  # 1, 1.5, 2.25 сек
                logger.debug("send_message retry attempt %s after %s: %s", attempt + 1, wait_sec, e)
                await asyncio.sleep(wait_sec)
        except Exception as e:
            logger.warning("send_message non-retryable error: %s", e)
            raise
    if last_err:
        logger.warning("send_message failed after %s attempts: %s", max_attempts, last_err)
        raise last_err


def handle_errors(handler):
    """Декоратор: перехватывает ошибки в хендлерах, логирует и уведомляет."""

    @wraps(handler)
    async def wrapper(update: object, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        try:
            return await handler(update, context, *args, **kwargs)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("Ошибка в хендлере %s:\n%s", handler.__name__, tb)

            if isinstance(update, Update) and update.effective_message:
                try:
                    for _ in range(3):
                        try:
                            await update.effective_message.reply_text(USER_MESSAGE, parse_mode=None)
                            break
                        except RETRYABLE_ERRORS:
                            await asyncio.sleep(1)
                except Exception:
                    pass

            if config.ADMIN_IDS and context.bot:
                try:
                    err_text = str(e).replace("`", "'")[:500]
                    short_tb = tb[-3500:] if len(tb) > 3500 else tb
                    text = f"{ADMIN_MESSAGE_PREFIX}**Текст ошибки:** `{err_text}`\n\n**Стек вызова:**\n```\n{short_tb}\n```"
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await send_message_with_retry(
                                context.bot, admin_id, text, parse_mode="Markdown"
                            )
                        except Exception:
                            pass
                except Exception as admin_err:
                    logger.warning("Не удалось отправить ошибку админу: %s", admin_err)
            raise

    return wrapper


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Глобальный обработчик ошибок PTB.
    Вызывается при любой необработанной ошибке.
    """
    error = context.error if context else None
    tb = (
        "".join(traceback.format_exception(type(error), error, error.__traceback__))
        if error
        else ""
    )
    logger.error("Глобальная ошибка: %s\n%s", error, tb)

    if update and isinstance(update, Update) and update.effective_message:
        try:
            for _ in range(3):
                try:
                    await update.effective_message.reply_text(USER_MESSAGE, parse_mode=None)
                    break
                except RETRYABLE_ERRORS:
                    await asyncio.sleep(1)
        except Exception:
            pass

    if config.ADMIN_IDS and context and hasattr(context, "bot") and context.bot:
        try:
            err_text = (str(error) if error else "Неизвестная ошибка").replace("`", "'")[:500]
            short_tb = tb[-3500:] if len(tb) > 3500 else tb
            text = f"{ADMIN_MESSAGE_PREFIX}**Текст ошибки:** `{err_text}`\n\n**Стек вызова:**\n```\n{short_tb}\n```"
            for admin_id in config.ADMIN_IDS:
                try:
                    await send_message_with_retry(
                        context.bot, admin_id, text, parse_mode="Markdown"
                    )
                except Exception:
                    pass
        except Exception as admin_err:
            logger.warning("Не удалось отправить ошибку админу: %s", admin_err)
