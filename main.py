"""
Главный файл запуска бота - точка входа
"""
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    filters,
    ContextTypes,
)
from telegram.request import HTTPXRequest

# Импорты модулей (config валидирует ключи при импорте — бот не запустится без них)
import config
from database import db
from handlers.basic import start_command, help_command, clear_command
from handlers.chat import handle_message
from handlers.media import handle_photo, handle_voice
from handlers.callbacks import button_callback
from handlers.commands import (
    translate_command, summarize_command, explain_command,
    quiz_command, calculator_command, wiki_command,
    random_command, code_command, persona_command, stats_command,
    image_command, settings_command
)
from handlers.admin import broadcast_command, users_command, logs_command
from handlers.payments import subscribe_command, pre_checkout_handler, successful_payment_handler
from handlers.conversation import get_wizard_conversation_handler
from utils.logging_config import setup_logging
from utils.error_middleware import global_error_handler

# Логирование с ротацией файлов (5 MB, 3 резервных копии)
setup_logging()
logger = logging.getLogger(__name__)


async def post_init(_application):
    """Вызывается после инициализации приложения (перед polling)"""
    await db.init()
    logger.info("База данных инициализирована")


async def post_shutdown(_application):
    """Вызывается после остановки приложения"""
    await db.close()
    logger.info("Соединение с базой данных закрыто")


def main():
    """Основная функция запуска бота"""
    logger.info("Инициализация бота...")
    # Конфигурация валидирована при импорте (pydantic-settings) — ключи обязательны

    # Создание приложения (post_init/post_shutdown для работы с БД)
    # Уменьшенные таймауты для быстрого отклика, увеличен pool для параллельных запросов
    try:
        request = HTTPXRequest(
            connect_timeout=10.0,
            read_timeout=25.0,
            write_timeout=15.0
        )
        
        application = Application.builder()\
            .token(config.TELEGRAM_BOT_TOKEN)\
            .request(request)\
            .connection_pool_size(8)\
            .get_updates_connection_pool_size(2)\
            .pool_timeout(30.0)\
            .post_init(post_init)\
            .post_shutdown(post_shutdown)\
            .build()
    except Exception as e:
        logger.warning(f"Не удалось настроить HTTPX ({e}), используем стандартные настройки")
        application = Application.builder()\
            .token(config.TELEGRAM_BOT_TOKEN)\
            .post_init(post_init)\
            .post_shutdown(post_shutdown)\
            .build()
    
    # Регистрация обработчиков команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("translate", translate_command))
    application.add_handler(CommandHandler("summarize", summarize_command))
    application.add_handler(CommandHandler("explain", explain_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("calculator", calculator_command))
    application.add_handler(CommandHandler("wiki", wiki_command))
    application.add_handler(CommandHandler("random", random_command))
    application.add_handler(CommandHandler("code", code_command))
    application.add_handler(CommandHandler("persona", persona_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("image", image_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # Регистрация обработчиков сообщений
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # ConversationHandler для /wizard (пошаговая настройка)
    application.add_handler(get_wizard_conversation_handler())
    # Обработчик callback кнопок
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Централизованная обработка ошибок: лог в файл + пользователю "Что-то пошло не так" + админу трейсбек
    application.add_error_handler(global_error_handler)
    
    # Запуск бота (run_polling управляет event loop самостоятельно)
    logger.info("Бот запущен...")
    logger.info("Найдите вашего бота в Telegram и отправьте /start")
    
    # timeout=5 — быстрее получать новые сообщения (long polling ждёт до 5 сек вместо 10)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        timeout=5,
        poll_interval=0
    )


if __name__ == '__main__':
    main()
