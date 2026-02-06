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
    filters,
    ContextTypes
)
from telegram.request import HTTPXRequest

# Импорты модулей
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

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)
    
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ Произошла ошибка при обработке запроса. Пожалуйста, попробуйте еще раз."
            )
        except:
            pass


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
    
    # Проверка конфигурации
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("Установите TELEGRAM_BOT_TOKEN в файле .env!")
        return
    
    if not config.GEMINI_API_KEY:
        logger.error("Установите ARTEMOX_API_KEY в файле .env!")
        return
    
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
    
    # Регистрация обработчиков сообщений
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Регистрация обработчика callback кнопок
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Глобальный обработчик ошибок
    application.add_error_handler(error_handler)
    
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
