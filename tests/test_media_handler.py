import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMediaHandler(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Create a dictionary of mocks for sys.modules to bypass import errors
        cls.module_patcher = patch.dict(
            sys.modules,
            {
                "telegram": MagicMock(),
                "telegram.error": MagicMock(),
                "telegram.constants": MagicMock(),
                "telegram.ext": MagicMock(),
                "structlog": MagicMock(),
                "sqlalchemy": MagicMock(),
                "httpx": MagicMock(),
                "pydantic": MagicMock(),
                "pydantic_settings": MagicMock(),
                "database": MagicMock(),
                "services.gemini": MagicMock(),
                "services.speech": MagicMock(),
                "services.image_gen": MagicMock(),
                "services.rag": MagicMock(),
                "services.memory": MagicMock(),
                "middlewares.rate_limit": MagicMock(),
                "middlewares.usage_limit": MagicMock(),
                "utils.text_tools": MagicMock(),
                "utils.analytics": MagicMock(),
                "config": MagicMock(),
                "handlers.chat": MagicMock(),
                "handlers.callbacks": MagicMock(),
                "handlers.commands": MagicMock(),
                "handlers.admin": MagicMock(),
                "handlers.documents": MagicMock(),
            },
        )
        cls.module_patcher.start()

        # Now import the handler
        # We need to make sure handlers.media is reloaded if it was already imported
        if "handlers.media" in sys.modules:
            del sys.modules["handlers.media"]

        import handlers.media

        cls.handler_module = handlers.media

    @classmethod
    def tearDownClass(cls):
        cls.module_patcher.stop()
        # Clean up to avoid affecting other tests
        if "handlers.media" in sys.modules:
            del sys.modules["handlers.media"]

    async def test_handle_photo_generation_trigger(self):
        """
        Test that handle_photo correctly identifies generation keywords
        and triggers the 'unimplemented' response instead of analysis.
        """
        handle_photo = self.handler_module.handle_photo

        # Setup mocks
        update = MagicMock()
        context = MagicMock()

        # Mock user
        user = MagicMock()
        user.id = 12345
        update.effective_user = user

        # Mock message
        message = MagicMock()
        update.message = message
        message.reply_text = AsyncMock()

        # Mock photo
        photo = MagicMock()
        photo.file_id = "test_file_id"
        message.photo = [photo]

        # Mock caption with generation keyword
        message.caption = "Сделай мне аватар"

        # Mock bot get_file
        file_mock = AsyncMock()
        context.bot.get_file = AsyncMock(return_value=file_mock)

        # We need to patch the objects as they exist in the imported module
        with (
            patch.object(
                self.handler_module.rate_limit_middleware,
                "check_rate_limit",
                new_callable=AsyncMock,
            ) as mock_rate_limit,
            patch.object(
                self.handler_module, "check_can_make_request", new_callable=AsyncMock
            ) as mock_check_usage,
            patch.object(
                self.handler_module.gemini_service, "analyze_image", new_callable=AsyncMock
            ) as mock_analyze,
        ):
            mock_rate_limit.return_value = True
            mock_check_usage.return_value = (True, None)

            # Run handler
            await handle_photo(update, context)

            # Verify
            message.reply_text.assert_called_with(
                "⚠️ Генерация изображений на основе фото пока не реализована"
            )
            mock_analyze.assert_not_called()

    async def test_handle_photo_analysis_trigger(self):
        """
        Test that handle_photo proceeds to analysis when no generation keywords are present.
        """
        handle_photo = self.handler_module.handle_photo

        # Setup mocks
        update = MagicMock()
        context = MagicMock()

        # Mock user
        user = MagicMock()
        user.id = 12345
        update.effective_user = user

        # Mock message
        message = MagicMock()
        update.message = message

        # Mock initial reply
        initial_msg = MagicMock()
        initial_msg.edit_text = AsyncMock()
        message.reply_text = AsyncMock(return_value=initial_msg)

        # Mock photo
        photo = MagicMock()
        photo.file_id = "test_file_id"
        message.photo = [photo]

        # Mock caption without generation keyword
        message.caption = "Что на фото?"

        # Mock bot get_file
        file_mock = MagicMock()
        file_mock.download_as_bytearray = AsyncMock(return_value=b"fake_image_bytes")
        context.bot.get_file = AsyncMock(return_value=file_mock)

        # Configure patches
        with (
            patch.object(
                self.handler_module.rate_limit_middleware,
                "check_rate_limit",
                new_callable=AsyncMock,
            ) as mock_rate_limit,
            patch.object(
                self.handler_module, "check_can_make_request", new_callable=AsyncMock
            ) as mock_check_usage,
            patch.object(
                self.handler_module.gemini_service, "analyze_image", new_callable=AsyncMock
            ) as mock_analyze,
            patch.object(
                self.handler_module, "sanitize_markdown", return_value="Sanitized Analysis"
            ),
            patch.object(self.handler_module, "track"),
        ):
            mock_rate_limit.return_value = True
            mock_check_usage.return_value = (True, None)
            mock_analyze.return_value = "Analysis Result"

            # Run handler
            await handle_photo(update, context)

            # Verify
            mock_analyze.assert_called_once()

            # Verify message flow
            message.reply_text.assert_any_call("📸 Анализирую изображение...")

            initial_msg.edit_text.assert_called_once()
            args, kwargs = initial_msg.edit_text.call_args
            assert "Sanitized Analysis" in args[0]
