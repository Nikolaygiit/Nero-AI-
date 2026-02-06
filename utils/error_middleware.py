"""
Централизованная обработка ошибок:
- Логирование в файл с трейсбеком
- Вежливое сообщение пользователю
- Отправка трейсбека админу
"""
import logging
import traceback
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

import config

logger = logging.getLogger(__name__)

USER_MESSAGE = "⚠️ Что-то пошло не так. Пожалуйста, попробуйте позже или напишите /help."
ADMIN_MESSAGE_PREFIX = "🐛 **Ошибка бота:**\n\n"


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
                    await update.effective_message.reply_text(USER_MESSAGE, parse_mode=None)
                except Exception:
                    pass

            if config.ADMIN_IDS:
                try:
                    short_tb = tb[-1500:] if len(tb) > 1500 else tb
                    text = f"{ADMIN_MESSAGE_PREFIX}```\n{short_tb}\n```"
                    for admin_id in config.ADMIN_IDS:
                        try:
                            await context.bot.send_message(
                                chat_id=admin_id,
                                text=text,
                                parse_mode="Markdown",
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
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__)) if error else ""
    logger.error("Глобальная ошибка: %s\n%s", error, tb)

    if update and isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(USER_MESSAGE, parse_mode=None)
        except Exception:
            pass

    if config.ADMIN_IDS and context and hasattr(context, "bot") and context.bot:
        try:
            short_tb = tb[-1500:] if len(tb) > 1500 else tb
            text = f"{ADMIN_MESSAGE_PREFIX}```\n{short_tb}\n```"
            for admin_id in config.ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass
        except Exception as admin_err:
            logger.warning("Не удалось отправить ошибку админу: %s", admin_err)
