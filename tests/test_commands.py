"""
Тесты для handlers.commands: run_gemini_command и команды, использующие его.
"""

import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Моки до импорта handlers
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["sqlalchemy.ext.asyncio"] = MagicMock()
sys.modules["sqlalchemy.orm"] = MagicMock()
sys.modules["pydantic"] = MagicMock()
sys.modules["pydantic_settings"] = MagicMock()
sys.modules["redis"] = MagicMock()
sys.modules["structlog"] = MagicMock()

mock_db = MagicMock()
mock_db.update_stats = AsyncMock()
sys.modules["database"] = MagicMock()
sys.modules["database.db"] = mock_db

sys.modules["config"] = MagicMock()
sys.modules["services.gemini"] = MagicMock()
sys.modules["services.image_gen"] = MagicMock()
sys.modules["services.llm_common"] = MagicMock()

mock_rate_limit = MagicMock()
mock_rate_limit.check_rate_limit = AsyncMock(return_value=True)
mock_rate_limit.time_window = 60
sys.modules["middlewares.rate_limit"] = MagicMock()
sys.modules["middlewares.rate_limit"].rate_limit_middleware = mock_rate_limit

sys.modules["utils.i18n"] = MagicMock()
sys.modules["utils.i18n"].t = lambda x, **kw: x
sys.modules["utils.analytics"] = MagicMock()
sys.modules["utils.text_tools"] = MagicMock()
sys.modules["utils.error_middleware"] = MagicMock()
sys.modules["utils.logging_config"] = MagicMock()

# Telegram как пакет (для utils.error_middleware и handlers)
telegram = types.ModuleType("telegram")
telegram.error = types.ModuleType("telegram.error")
telegram.error.NetworkError = Exception
telegram.error.BadRequest = Exception
telegram.ext = types.ModuleType("telegram.ext")
telegram.ext.ContextTypes = MagicMock()
telegram.Update = MagicMock()
telegram.InlineKeyboardButton = MagicMock()
telegram.InlineKeyboardMarkup = MagicMock()
ctx_types = MagicMock()
ctx_types.DEFAULT_TYPE = MagicMock()
telegram.ext.ContextTypes = ctx_types
sys.modules["telegram"] = telegram
sys.modules["telegram.error"] = telegram.error
sys.modules["telegram.ext"] = telegram.ext

sys.modules["middlewares.usage_limit"] = MagicMock()
sys.modules["middlewares.ban_check"] = MagicMock()
sys.modules["services.memory"] = MagicMock()
sys.modules["services.rag"] = MagicMock()

# Импорт commands через handlers
from handlers import commands  # noqa: E402, I001

# Объекты для тестов
mock_message = MagicMock()
mock_message.reply_text = AsyncMock()
mock_message.reply_chat_action = AsyncMock()
mock_update = MagicMock()
mock_update.effective_user = MagicMock(id=123)
mock_update.message = mock_message


@pytest.mark.asyncio
async def test_run_gemini_command_success():
    """При успешном generate_content отправляется ответ и вызывается update_stats."""
    mock_gemini = AsyncMock(return_value="Перевод: Hello")
    mock_db.update_stats.reset_mock()
    mock_message.reply_text.reset_mock()
    mock_message.reply_chat_action.reset_mock()

    with (
        patch.object(commands, "gemini_service", MagicMock(generate_content=mock_gemini)),
        patch.object(commands, "db", mock_db),
    ):
        result = await commands.run_gemini_command(
            mock_update,
            user_id=123,
            prompt="Translate: Привет",
            success_formatter=lambda r: f"Result: {r}",
            command_name="translate",
            error_prefix="Ошибка перевода",
        )

    assert result is True
    mock_gemini.assert_called_once_with("Translate: Привет", user_id=123, use_context=False)
    mock_message.reply_chat_action.assert_called_once_with("typing")
    mock_message.reply_text.assert_called_once()
    call_args = mock_message.reply_text.call_args
    assert "Result: Перевод: Hello" in str(call_args)
    mock_db.update_stats.assert_called_once_with(123, command="translate")


@pytest.mark.asyncio
async def test_run_gemini_command_rate_limit():
    """При превышении rate limit отправляется сообщение, generate_content не вызывается."""
    mock_gemini = AsyncMock()
    mock_message.reply_text.reset_mock()
    rate_limit_strict = MagicMock()
    rate_limit_strict.check_rate_limit = AsyncMock(return_value=False)
    rate_limit_strict.time_window = 60

    with (
        patch.object(commands, "rate_limit_middleware", rate_limit_strict),
        patch.object(commands, "gemini_service", MagicMock(generate_content=mock_gemini)),
    ):
        result = await commands.run_gemini_command(
            mock_update,
            user_id=123,
            prompt="Any",
            success_formatter=lambda r: r,
            command_name="translate",
        )

    assert result is True
    mock_gemini.assert_not_called()
    mock_message.reply_text.assert_called_once()
    call_args = mock_message.reply_text.call_args[0][0]
    assert "Подождите" in call_args or "секунд" in call_args


@pytest.mark.asyncio
async def test_run_gemini_command_on_error_replies_and_returns_true():
    """При исключении из generate_content отправляется сообщение об ошибке."""
    mock_gemini = AsyncMock(side_effect=Exception("API error"))
    mock_message.reply_text.reset_mock()

    with patch.object(commands, "gemini_service", MagicMock(generate_content=mock_gemini)):
        result = await commands.run_gemini_command(
            mock_update,
            user_id=123,
            prompt="Fail",
            success_formatter=lambda r: r,
            command_name="translate",
            error_prefix="Ошибка перевода",
        )

    assert result is True
    mock_message.reply_text.assert_called_once()
    call_args = mock_message.reply_text.call_args[0][0]
    assert "Ошибка перевода" in call_args
    assert "API error" in call_args
