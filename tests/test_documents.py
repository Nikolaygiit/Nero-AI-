import unittest
import sys
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

# Mock external dependencies before importing anything
# We must mock submodules of packages that are imported in handlers/__init__.py

# Mock telegram
mock_telegram = MagicMock()
mock_telegram.Update = MagicMock()
sys.modules['telegram'] = mock_telegram
sys.modules['telegram.ext'] = MagicMock()
sys.modules['telegram.constants'] = MagicMock()
sys.modules['telegram.error'] = MagicMock()

# Mock database
mock_database = MagicMock()
mock_db = MagicMock()
mock_database.db = mock_db
sys.modules['database'] = mock_database
sys.modules['database.db'] = mock_db
sys.modules['database.models'] = MagicMock()

# Mock services
# We don't mock 'services' itself to allow package import, but we mock its submodules
sys.modules['services.gemini'] = MagicMock()
sys.modules['services.image_gen'] = MagicMock()
sys.modules['services.memory'] = MagicMock()
sys.modules['services.speech'] = MagicMock()

# Mock services.rag
mock_rag = MagicMock()
sys.modules['services.rag'] = mock_rag

# Mock middlewares
# We don't mock 'middlewares' itself, but its submodules
mock_rate_limit_module = MagicMock()
sys.modules['middlewares.rate_limit'] = mock_rate_limit_module

mock_usage_limit_module = MagicMock()
sys.modules['middlewares.usage_limit'] = mock_usage_limit_module

# Mock utils
sys.modules['utils'] = MagicMock()
sys.modules['utils.text_tools'] = MagicMock()
sys.modules['utils.analytics'] = MagicMock()
sys.modules['utils.formatting'] = MagicMock()
sys.modules['utils.helpers'] = MagicMock()

# Mock other heavy dependencies
sys.modules['sqlalchemy'] = MagicMock()
sys.modules['sqlalchemy.ext.asyncio'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['chromadb'] = MagicMock()
sys.modules['langchain'] = MagicMock()
sys.modules['pypdf'] = MagicMock()
sys.modules['pydantic'] = MagicMock()
sys.modules['pydantic_settings'] = MagicMock()

# Mock config
sys.modules['config'] = MagicMock()

# Mock sibling handlers to avoid importing their dependencies (like structlog, openai, etc.)
sys.modules['handlers.basic'] = MagicMock()
sys.modules['handlers.chat'] = MagicMock()
sys.modules['handlers.media'] = MagicMock()
sys.modules['handlers.callbacks'] = MagicMock()
sys.modules['handlers.commands'] = MagicMock()

# Now import the module under test
try:
    from handlers import documents
except ImportError as e:
    print(f"Failed to import handlers.documents: {e}")
    raise

class TestDocumentsHandler(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Setup common mock behavior for Update and Context
        self.update = MagicMock()
        self.context = MagicMock()
        self.user_id = 12345
        self.update.effective_user.id = self.user_id
        self.update.message.reply_text = AsyncMock()
        self.update.message.document = MagicMock()
        self.update.message.document.file_name = "test.pdf"
        self.update.message.document.file_size = 1024
        self.update.message.document.file_id = "file_123"

        # Mock file download
        self.file_mock = MagicMock()
        self.file_mock.download_as_bytearray = AsyncMock(return_value=b"PDF content")
        self.context.bot.get_file = AsyncMock(return_value=self.file_mock)

        # Mock status message (returned by reply_text)
        self.status_msg = MagicMock()
        self.status_msg.edit_text = AsyncMock()
        self.update.message.reply_text.return_value = self.status_msg

        # Patch dependencies in handlers.documents

        # Patch db
        self.db_patcher = patch('handlers.documents.db')
        self.mock_db = self.db_patcher.start()
        self.mock_db.is_banned = AsyncMock(return_value=False)

        # Patch rate_limit_middleware
        self.rate_limit_patcher = patch('handlers.documents.rate_limit_middleware')
        self.mock_rl_middleware = self.rate_limit_patcher.start()
        self.mock_rl_middleware.check_rate_limit = AsyncMock(return_value=True)

        # Patch check_can_make_request
        self.usage_limit_patcher = patch('handlers.documents.check_can_make_request', new_callable=AsyncMock)
        self.mock_check_usage = self.usage_limit_patcher.start()
        self.mock_check_usage.return_value = (True, "")

        # Patch add_pdf_document
        self.add_pdf_patcher = patch('handlers.documents.add_pdf_document', new_callable=AsyncMock)
        self.mock_add_pdf = self.add_pdf_patcher.start()
        self.mock_add_pdf.return_value = (True, "Processed")

    async def asyncTearDown(self):
        self.db_patcher.stop()
        self.rate_limit_patcher.stop()
        self.usage_limit_patcher.stop()
        self.add_pdf_patcher.stop()

    async def test_handle_document_banned_user(self):
        """Test that banned users are blocked."""
        self.mock_db.is_banned.return_value = True

        await documents.handle_document(self.update, self.context)

        # Verify ban message
        self.update.message.reply_text.assert_called_with("⛔ Вы заблокированы.")
        # Verify no processing happened
        self.mock_add_pdf.assert_not_called()

    async def test_handle_document_no_document(self):
        """Test handling when document is missing."""
        self.update.message.document = None

        await documents.handle_document(self.update, self.context)

        # Should return early
        self.mock_add_pdf.assert_not_called()

    async def test_handle_document_non_pdf(self):
        """Test that non-PDF files are rejected."""
        self.update.message.document.file_name = "image.jpg"

        await documents.handle_document(self.update, self.context)

        # Verify support message
        args, kwargs = self.update.message.reply_text.call_args
        self.assertIn("поддерживаются только **PDF**-файлы", args[0])
        self.mock_add_pdf.assert_not_called()

    async def test_handle_document_too_large(self):
        """Test that large files are rejected."""
        # Max size is 20MB. Set size to 21MB
        self.update.message.document.file_size = 21 * 1024 * 1024

        await documents.handle_document(self.update, self.context)

        # Verify size limit message
        args, kwargs = self.update.message.reply_text.call_args
        self.assertIn("Файл слишком большой", args[0])
        self.mock_add_pdf.assert_not_called()

    async def test_handle_document_rate_limited(self):
        """Test that rate limited requests are blocked."""
        self.mock_rl_middleware.check_rate_limit.return_value = False

        await documents.handle_document(self.update, self.context)

        # Verify rate limit message
        args, kwargs = self.update.message.reply_text.call_args
        self.assertIn("Слишком много запросов", args[0])
        self.mock_add_pdf.assert_not_called()

    async def test_handle_document_usage_limited(self):
        """Test that usage limited requests are blocked."""
        self.mock_check_usage.return_value = (False, "Limit reached")

        await documents.handle_document(self.update, self.context)

        # Verify limit message
        self.update.message.reply_text.assert_called_with("Limit reached", parse_mode=None)
        self.mock_add_pdf.assert_not_called()

    async def test_handle_document_success(self):
        """Test successful document processing."""
        await documents.handle_document(self.update, self.context)

        # Verify status message
        self.update.message.reply_text.assert_called_with("📄 Читаю PDF и добавляю в базу знаний...")

        # Verify file download
        self.context.bot.get_file.assert_called_with("file_123")
        self.file_mock.download_as_bytearray.assert_called_once()

        # Verify RAG processing
        self.mock_add_pdf.assert_called_with(self.user_id, b"PDF content", "test.pdf")

        # Verify success message
        self.status_msg.edit_text.assert_called_with("Processed", parse_mode=None)

    async def test_handle_document_processing_exception(self):
        """Test exception handling during processing."""
        # Make processing raise an exception
        self.mock_add_pdf.side_effect = Exception("Processing error")

        await documents.handle_document(self.update, self.context)

        # Verify status message was initially sent
        self.update.message.reply_text.assert_called_with("📄 Читаю PDF и добавляю в базу знаний...")

        # Verify error message
        args, kwargs = self.status_msg.edit_text.call_args
        self.assertIn("Ошибка обработки PDF", args[0])
        self.assertIn("Processing error", args[0])

if __name__ == '__main__':
    unittest.main()
