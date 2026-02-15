import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

# Mock dependencies before import
sys.modules["telegram"] = MagicMock()
sys.modules["telegram.ext"] = MagicMock()
sys.modules["telegram.error"] = MagicMock()  # Mock telegram.error
sys.modules["telegram.constants"] = MagicMock()  # Mock telegram.constants

sys.modules["database"] = MagicMock()
sys.modules["services.gemini"] = MagicMock()
sys.modules["services.image_gen"] = MagicMock()
sys.modules["middlewares.rate_limit"] = MagicMock()
sys.modules["utils.i18n"] = MagicMock()
sys.modules["config"] = MagicMock()
sys.modules["tasks.image_tasks"] = MagicMock()
sys.modules["tasks.broker"] = MagicMock()

# Mock internal modules to avoid import side-effects
sys.modules["handlers.basic"] = MagicMock()
sys.modules["handlers.chat"] = MagicMock()
sys.modules["handlers.media"] = MagicMock()
sys.modules["handlers.callbacks"] = MagicMock()

# Mock specific attributes needed for import or execution
sys.modules["telegram"].Update = MagicMock()
sys.modules["telegram.ext"].ContextTypes = MagicMock()
sys.modules["telegram.ext"].ContextTypes.DEFAULT_TYPE = MagicMock()
sys.modules["database"].db = AsyncMock()
sys.modules["services.gemini"].gemini_service = AsyncMock()
sys.modules["services.image_gen"].image_generator = MagicMock()
sys.modules["middlewares.rate_limit"].rate_limit_middleware = AsyncMock()
sys.modules["utils.i18n"].t = lambda key, **kwargs: key
sys.modules["config"].PERSONAS = {}  # Mock empty personas

# Now import the module under test
from handlers.commands import translate_command  # noqa: E402


class TestTranslateCommand(unittest.IsolatedAsyncioTestCase):
    async def test_translate_command_validation_empty_args(self):
        # Setup
        update = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.args = []

        # Execute
        await translate_command(update, context)

        # Verify
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        self.assertIn("Укажите язык и текст для перевода", args[0])
        self.assertEqual(kwargs.get("parse_mode"), "Markdown")

    async def test_translate_command_validation_insufficient_args(self):
        # Setup
        update = MagicMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.args = ["en"]  # Only language, no text

        # Execute
        await translate_command(update, context)

        # Verify
        update.message.reply_text.assert_called_once()
        args, kwargs = update.message.reply_text.call_args
        self.assertIn("Укажите язык и текст для перевода", args[0])
        self.assertEqual(kwargs.get("parse_mode"), "Markdown")

    async def test_translate_command_success(self):
        # Setup
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        update.message.reply_chat_action = AsyncMock()
        update.effective_user.id = 12345

        context = MagicMock()
        context.args = ["en", "hello"]

        # Mock dependencies
        sys.modules[
            "middlewares.rate_limit"
        ].rate_limit_middleware.check_rate_limit.return_value = True
        sys.modules["services.gemini"].gemini_service.generate_content.return_value = "Hello"

        # Execute
        await translate_command(update, context)

        # Verify
        # Check rate limit called
        sys.modules[
            "middlewares.rate_limit"
        ].rate_limit_middleware.check_rate_limit.assert_called_with(12345)

        # Check gemini called
        sys.modules["services.gemini"].gemini_service.generate_content.assert_called_with(
            "Переведи следующий текст на en: hello. Верни только перевод без дополнительных комментариев.",
            12345,
            use_context=False,
        )

        # Check reply
        update.message.reply_text.assert_called()
        # Verify translation reply
        found_translation = False
        for call in update.message.reply_text.call_args_list:
            args, _ = call
            if "Hello" in args[0] and "Перевод готов" in args[0]:
                found_translation = True
                break
        self.assertTrue(found_translation)

        # Check stats updated
        sys.modules["database"].db.update_stats.assert_called_with(12345, command="translate")


if __name__ == "__main__":
    unittest.main()
