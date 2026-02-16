"""
Общие моки для тестов: config, db, telegram, middlewares, utils.
Использование: вызвать setup_handler_mocks() до импорта handlers.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock


def make_mock_db():
    mock = MagicMock()
    mock.update_stats = AsyncMock()
    mock.get_user = AsyncMock(return_value=None)
    mock.get_user_messages = AsyncMock(return_value=[])
    mock.add_message = AsyncMock()
    mock.is_banned = AsyncMock(return_value=False)
    mock.create_or_update_user = AsyncMock()
    mock.increment_daily_usage = AsyncMock()
    mock.get_stats = AsyncMock(return_value=None)
    return mock


def make_mock_config():
    mock = MagicMock()
    mock.GEMINI_API_KEY = "test_key"
    mock.GEMINI_API_BASE = "http://test.base"
    mock.PREFERRED_MODELS = ["model-a"]
    mock.PERSONAS = {"assistant": {"prompt": "You are helpful."}}
    mock.MAX_TOKENS_PER_REQUEST = 100
    mock.MODEL_TIMEOUT_SEC = 10
    mock.settings = MagicMock()
    mock.settings.DEEPSEEK_API_KEY = ""
    mock.settings.OPENAI_API_KEY = ""
    mock.settings.TELEGRAM_BOT_TOKEN = "test_token"
    mock.settings.ARTEMOX_API_KEY = "test_key"
    return mock


def make_telegram_mocks():
    """Регистрирует telegram и telegram.ext в sys.modules с нужными атрибутами."""
    telegram = types.ModuleType("telegram")
    telegram.error = types.ModuleType("telegram.error")
    telegram.error.NetworkError = Exception
    telegram.error.BadRequest = Exception
    telegram.ext = types.ModuleType("telegram.ext")
    telegram.Update = MagicMock()
    telegram.InlineKeyboardButton = MagicMock()
    telegram.InlineKeyboardMarkup = MagicMock()
    ctx_types = MagicMock()
    ctx_types.DEFAULT_TYPE = MagicMock()
    telegram.ext.ContextTypes = ctx_types
    sys.modules["telegram"] = telegram
    sys.modules["telegram.error"] = telegram.error
    sys.modules["telegram.ext"] = telegram.ext
    return telegram


def setup_core_mocks():
    """Базовые моки: sqlalchemy, pydantic, redis, structlog, database, config."""
    sys.modules.setdefault("sqlalchemy", MagicMock())
    sys.modules.setdefault("sqlalchemy.ext.asyncio", MagicMock())
    sys.modules.setdefault("sqlalchemy.orm", MagicMock())
    sys.modules.setdefault("pydantic", MagicMock())
    sys.modules.setdefault("pydantic_settings", MagicMock())
    sys.modules.setdefault("redis", MagicMock())
    sys.modules.setdefault("structlog", MagicMock())
    mock_db = make_mock_db()
    _db_module = MagicMock()
    _db_module.db = mock_db
    sys.modules["database"] = _db_module
    sys.modules["database.db"] = mock_db
    mock_config = make_mock_config()
    sys.modules["config"] = mock_config
    return mock_db, mock_config


def setup_handler_mocks():
    """Полный набор моков для импорта handlers (commands, chat, callbacks)."""
    mock_db, mock_config = setup_core_mocks()
    sys.modules.setdefault("services.gemini", MagicMock())
    sys.modules.setdefault("services.image_gen", MagicMock())
    sys.modules.setdefault("services.llm_common", MagicMock())
    mock_rate = MagicMock()
    mock_rate.check_rate_limit = AsyncMock(return_value=True)
    mock_rate.time_window = 60
    mock_rate.max_requests = 30
    sys.modules["middlewares.rate_limit"] = MagicMock()
    sys.modules["middlewares.rate_limit"].rate_limit_middleware = mock_rate
    sys.modules.setdefault("utils.i18n", MagicMock())
    sys.modules["utils.i18n"].t = lambda x, **kw: x
    sys.modules.setdefault("utils.analytics", MagicMock())
    sys.modules.setdefault("utils.text_tools", MagicMock())
    sys.modules.setdefault("utils.error_middleware", MagicMock())
    sys.modules.setdefault("utils.logging_config", MagicMock())
    make_telegram_mocks()
    sys.modules.setdefault("middlewares.usage_limit", MagicMock())
    sys.modules["middlewares.usage_limit"].check_can_make_request = AsyncMock(
        return_value=(True, "")
    )
    sys.modules.setdefault("middlewares.ban_check", MagicMock())
    _mem = MagicMock()
    _mem.extract_and_save_facts = AsyncMock()
    sys.modules.setdefault("services.memory", _mem)
    sys.modules.setdefault("services.rag", MagicMock())
    return mock_db, mock_config


def make_mock_update(user_id=123, text="Hello", chat_id=456):
    """Фикстура Update с message и effective_user."""
    update = MagicMock()
    update.effective_user = MagicMock(id=user_id, first_name="Test", username="test")
    update.effective_chat = MagicMock(id=chat_id)
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.message.reply_chat_action = AsyncMock()
    update.message.edit_text = AsyncMock()
    update.message.delete = AsyncMock()
    update.message.reply_photo = AsyncMock()
    return update


def make_mock_context(user_data=None):
    """Фикстура Context с user_data."""
    context = MagicMock()
    context.user_data = user_data if user_data is not None else {}
    return context
