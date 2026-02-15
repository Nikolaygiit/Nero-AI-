"""
Интерактивное меню — ConversationHandler (FSM)
Пошаговые сценарии: настройки, выбор персонажа
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
)

import config
from database import db

logger = logging.getLogger(__name__)

CHOOSE_PERSONA, CHOOSE_MODEL, CONFIRM = range(3)


async def wizard_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало пошаговой настройки"""
    await update.message.reply_text(
        "⚙️ **Пошаговая настройка**\n\nСейчас выберите персонажа:",
        parse_mode="Markdown",
    )
    keyboard = [
        [
            InlineKeyboardButton("🎓 Учитель", callback_data="wizard_persona_teacher"),
            InlineKeyboardButton("💻 Программист", callback_data="wizard_persona_programmer"),
        ],
        [
            InlineKeyboardButton("🤝 Помощник", callback_data="wizard_persona_assistant"),
            InlineKeyboardButton("🎨 Креативщик", callback_data="wizard_persona_creative"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="wizard_cancel")],
    ]
    await update.message.reply_text(
        "Выберите персонажа:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return CHOOSE_PERSONA


async def wizard_persona_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора персонажа в wizard"""
    query = update.callback_query
    await query.answer()
    if query.data == "wizard_cancel":
        await query.edit_message_text("Настройка отменена.")
        return ConversationHandler.END
    if query.data.startswith("wizard_persona_"):
        persona = query.data.replace("wizard_persona_", "")
        if persona in config.PERSONAS:
            context.user_data["wizard_persona"] = persona
            await db.create_or_update_user(telegram_id=query.from_user.id, persona=persona)
            name = config.PERSONAS[persona]["name"]
            await query.edit_message_text(
                f"✅ Персонаж: **{name}**\n\nНастройка завершена!", parse_mode="Markdown"
            )
            return ConversationHandler.END
    return CHOOSE_PERSONA


async def wizard_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена wizard"""
    await update.message.reply_text("Настройка отменена.")
    return ConversationHandler.END


def get_wizard_conversation_handler() -> ConversationHandler:
    """ConversationHandler для /wizard — пошаговая настройка"""
    from telegram.ext import CallbackQueryHandler, CommandHandler

    return ConversationHandler(
        entry_points=[CommandHandler("wizard", wizard_start)],
        states={
            CHOOSE_PERSONA: [
                CallbackQueryHandler(wizard_persona_callback, pattern="^wizard_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", wizard_cancel)],
        per_message=True,  # CallbackQueryHandler отслеживается по каждому сообщению (убирает PTBUserWarning)
    )
