"""
Админ-панель: /broadcast, /users, /logs
"""
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from database import db
import config

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in config.ADMIN_IDS if config.ADMIN_IDS else False


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рассылка сообщения всем пользователям: /broadcast <текст>"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Команда доступна только администраторам.")
        return

    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "📢 Использование: /broadcast <сообщение>\n\n"
            "Пример: /broadcast Добрый день! Добавлена новая функция."
        )
        return

    try:
        users_count = await db.get_users_count()
        success = 0
        failed = 0

        status_msg = await update.message.reply_text(f"📤 Рассылка {users_count} пользователям...")

        async for chunk in db.get_all_telegram_ids():
            for tg_id in chunk:
                try:
                    await context.bot.send_message(
                        chat_id=tg_id,
                        text=f"📢 **Объявление:**\n\n{text}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    success += 1
                except Exception as e:
                    failed += 1
                    logger.warning(f"Broadcast failed for {tg_id}: {e}")

        await status_msg.edit_text(
            f"✅ Рассылка завершена!\n\n"
            f"Доставлено: {success}\n"
            f"Не доставлено: {failed}"
        )
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        await update.message.reply_text(f"❌ Ошибка рассылки: {str(e)[:200]}")


async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика пользователей: /users"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Команда доступна только администраторам.")
        return

    try:
        count = await db.get_users_count()
        await update.message.reply_text(
            f"👥 **Статистика бота:**\n\n"
            f"Всего пользователей: {count}",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"Users command error: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}")


async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получить файл логов: /logs"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Команда доступна только администраторам.")
        return

    log_path = Path("bot.log")
    if not log_path.exists():
        await update.message.reply_text("📋 Файл логов не найден.")
        return

    try:
        # Отправляем последние 50KB логов
        size = log_path.stat().st_size
        with open(log_path, "rb") as f:
            if size > 48000:
                f.seek(size - 48000)
            doc_content = f.read()

        temp_log = Path("bot_logs_send.txt")
        temp_log.write_bytes(doc_content)

        with open(temp_log, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename="bot_logs.txt",
                caption="📋 Последние логи бота"
            )
        temp_log.unlink(missing_ok=True)
    except Exception as e:
        logger.error(f"Logs command error: {e}")
        await update.message.reply_text(f"❌ Ошибка отправки логов: {str(e)[:200]}")
