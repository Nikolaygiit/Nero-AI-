import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestChatUtils(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Define mocks
        mocks = {
            "telegram": MagicMock(),
            "telegram.ext": MagicMock(),
            "telegram.error": MagicMock(),
            "telegram.constants": MagicMock(),
            "structlog": MagicMock(),
            "database": MagicMock(),
            "services": MagicMock(),
            "services.gemini": MagicMock(),
            "services.image_gen": MagicMock(),
            "services.memory": MagicMock(),
            "services.rag": MagicMock(),
            "tasks": MagicMock(),
            "tasks.image_tasks": MagicMock(),
            "tasks.broker": MagicMock(),
            "middlewares": MagicMock(),
            "middlewares.rate_limit": MagicMock(),
            "middlewares.usage_limit": MagicMock(),
            "utils": MagicMock(),
            "utils.text_tools": MagicMock(),
            "utils.analytics": MagicMock(),
            "utils.i18n": MagicMock(),
            "config": MagicMock(),
            "handlers.basic": MagicMock(),
            "handlers.media": MagicMock(),
            "handlers.callbacks": MagicMock(),
            "handlers.commands": MagicMock(),
            "handlers.chat": MagicMock(),
        }

        cls.modules_patcher = patch.dict(sys.modules, mocks)
        cls.modules_patcher.start()

        # Force reload if already imported
        if "handlers.chat_utils" in sys.modules:
            del sys.modules["handlers.chat_utils"]

        global \
            is_image_request, \
            extract_image_prompt, \
            handle_multimodal_request, \
            gemini_service, \
            sanitize_markdown
        from handlers.chat_utils import (
            extract_image_prompt,
            gemini_service,
            handle_multimodal_request,
            is_image_request,
            sanitize_markdown,
        )

    @classmethod
    def tearDownClass(cls):
        cls.modules_patcher.stop()

    def test_is_image_request(self):
        self.assertTrue(is_image_request("нарисуй кота"))
        self.assertFalse(is_image_request("привет"))
        self.assertTrue(is_image_request("создай картинку"))
        self.assertTrue(is_image_request("сгенерируй"))

    def test_extract_image_prompt(self):
        self.assertEqual(extract_image_prompt("нарисуй кота"), "кота")
        self.assertEqual(extract_image_prompt("нарисуй"), "красивое изображение")


class TestChatUtilsAsync(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # We rely on the imports from TestChatUtils setUpClass context if running together?
        # No, IsolatedAsyncioTestCase is separate.
        # We need to apply patches here too or ensure they are applied.
        # Since we are running the file as script, the global scope matters.
        # But if we use setUpClass in TestChatUtils, it only applies to that class.
        pass

    @classmethod
    def setUpClass(cls):
        # Same patching needed here
        mocks = {
            "telegram": MagicMock(),
            "telegram.ext": MagicMock(),
            "telegram.error": MagicMock(),
            "telegram.constants": MagicMock(),
            "structlog": MagicMock(),
            "database": MagicMock(),
            "services": MagicMock(),
            "services.gemini": MagicMock(),
            "services.image_gen": MagicMock(),
            "services.memory": MagicMock(),
            "services.rag": MagicMock(),
            "tasks": MagicMock(),
            "tasks.image_tasks": MagicMock(),
            "tasks.broker": MagicMock(),
            "middlewares": MagicMock(),
            "middlewares.rate_limit": MagicMock(),
            "middlewares.usage_limit": MagicMock(),
            "utils": MagicMock(),
            "utils.text_tools": MagicMock(),
            "utils.analytics": MagicMock(),
            "utils.i18n": MagicMock(),
            "config": MagicMock(),
            "handlers.basic": MagicMock(),
            "handlers.media": MagicMock(),
            "handlers.callbacks": MagicMock(),
            "handlers.commands": MagicMock(),
            "handlers.chat": MagicMock(),
        }

        cls.modules_patcher = patch.dict(sys.modules, mocks)
        cls.modules_patcher.start()

        if "handlers.chat_utils" in sys.modules:
            del sys.modules["handlers.chat_utils"]

        global handle_multimodal_request, gemini_service, sanitize_markdown
        from handlers.chat_utils import gemini_service, handle_multimodal_request, sanitize_markdown

    @classmethod
    def tearDownClass(cls):
        cls.modules_patcher.stop()

    async def test_handle_multimodal_request_no_image(self):
        update = MagicMock()
        context = MagicMock()
        context.user_data = {}  # No image

        result = await handle_multimodal_request(update, context)
        self.assertFalse(result)

    async def test_handle_multimodal_request_with_image(self):
        update = MagicMock()
        update.effective_user.id = 123
        update.message.text = "Что на картинке?"
        update.message.reply_chat_action = AsyncMock()
        update.message.reply_text = AsyncMock()

        context = MagicMock()
        context.user_data = {"last_image_base64": "base64str"}

        # Setup mocks
        gemini_service.generate_with_image_context = AsyncMock(return_value="Это кот")
        sanitize_markdown.return_value = "Это кот"

        result = await handle_multimodal_request(update, context)

        self.assertTrue(result)
        gemini_service.generate_with_image_context.assert_called_once()
        self.assertNotIn("last_image_base64", context.user_data)
        update.message.reply_text.assert_called_once()


if __name__ == "__main__":
    unittest.main()
