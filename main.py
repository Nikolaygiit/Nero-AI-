"""
Главный файл запуска бота - точка входа
"""

import structlog
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)
from telegram.request import HTTPXRequest

# Импорты модулей (config валидирует ключи при импорте — бот не запустится без них)
import config
from database import db
from handlers.admin import broadcast_command, logs_command, users_command
from handlers.basic import clear_command, help_command, start_command
from handlers.callbacks import button_callback
from handlers.chat import handle_message
from handlers.commands import (
    calculator_command,
    code_command,
    explain_command,
    image_command,
    persona_command,
    quiz_command,
    random_command,
    settings_command,
    stats_command,
    summarize_command,
    translate_command,
    wiki_command,
)
from handlers.conversation import get_wizard_conversation_handler
from handlers.documents import handle_document, rag_clear_command, rag_docs_command
from handlers.media import handle_photo, handle_voice
from handlers.payments import pre_checkout_handler, subscribe_command, successful_payment_handler
from utils.error_middleware import global_error_handler
from utils.logging_config import setup_logging

# Логирование с ротацией файлов (5 MB, 3 резервных копии) через structlog
setup_logging()
logger = structlog.get_logger(__name__)

# Observability: Prometheus metrics (если prometheus_client установлен)
try:
    from utils.metrics import PROMETHEUS_AVAILABLE, start_metrics_server

    if PROMETHEUS_AVAILABLE:
        _mp = getattr(config.settings, "METRICS_PORT", 9090)
        start_metrics_server(_mp)
        logger.info("metrics_server_started", port=_mp)
except Exception as e:
    logger.debug("metrics_disabled", error=str(e))


async def post_init(_application):
    """Вызывается после инициализации приложения (перед polling)"""
    await db.init()
    logger.info("database_initialized")


async def post_shutdown(_application):
    """Вызывается после остановки приложения"""
    await db.close()
    logger.info("database_closed")


def main():
    """Основная функция запуска бота"""
    logger.info("bot_initializing")
    # Конфигурация валидирована при импорте (pydantic-settings) — ключи обязательны

    # Создание приложения: таймауты в HTTPXRequest, pool — только без custom request
    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=25.0,
        write_timeout=15.0,
    )
    application = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .request(request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

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
    application.add_handler(CommandHandler("docs", rag_docs_command))
    application.add_handler(CommandHandler("docs_clear", rag_clear_command))
    application.add_handler(PreCheckoutQueryHandler(pre_checkout_handler))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))

    # Регистрация обработчиков сообщений
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # ConversationHandler для /wizard (пошаговая настройка)
    application.add_handler(get_wizard_conversation_handler())
    # Обработчик callback кнопок
    application.add_handler(CallbackQueryHandler(button_callback))

    # Централизованная обработка ошибок: лог в файл + пользователю "Что-то пошло не так" + админу трейсбек
    application.add_error_handler(global_error_handler)

    # Запуск: webhooks (high load) или polling (разработка)
    use_webhooks = getattr(config.settings, "USE_WEBHOOKS", False)
    webhook_url = getattr(config.settings, "WEBHOOK_URL", "").strip()

    if use_webhooks and webhook_url:
        port = getattr(config.settings, "WEBHOOK_PORT", 8443)
        base = webhook_url.rstrip("/")
        full_webhook = f"{base}/webhook" if not base.endswith("/webhook") else base
        logger.info("bot_started_webhook", webhook_url=full_webhook, port=port)
        application.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=full_webhook,
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )
    else:
        logger.info("bot_started", message="Бот запущен (polling), ожидает сообщения")
        application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True, timeout=5, poll_interval=0)


if __name__ == "__main__":
    main()
