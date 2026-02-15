import sys
import os
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

# Add current dir to path
sys.path.append(os.getcwd())

# Mock dependencies before importing services.rag
sys.modules['pypdf'] = MagicMock()
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['config'] = MagicMock()
sys.modules['sqlalchemy'] = MagicMock()
sys.modules['database'] = MagicMock()
sys.modules['database.db'] = MagicMock()
sys.modules['database.models'] = MagicMock()

# Mock services.gemini because services/__init__.py might import it
sys.modules['services.gemini'] = MagicMock()
sys.modules['services.image_gen'] = MagicMock()
sys.modules['services.memory'] = MagicMock()
# But NOT services.rag, as we want to import it (or reload it)

# Mock attributes on config
sys.modules['config'].GEMINI_API_BASE = "https://api.example.com"
sys.modules['config'].GEMINI_API_KEY = "dummy_key"
sys.modules['config'].RAG_CHROMA_PATH = "/tmp/chroma"
sys.modules['config'].RAG_EMBEDDING_MODEL = "embedding-001"

# Now import the module under test
if 'services.rag' in sys.modules:
    del sys.modules['services.rag']
# Also delete services package if loaded, to force re-import logic if needed
if 'services' in sys.modules:
    del sys.modules['services']
# Wait, if I delete services package, I lose my mocks for services.gemini inside it?
# No, sys.modules['services.gemini'] is independent key.
# But importing services might trigger importing services.gemini.

import services.rag

class TestRagService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Reset mocks
        services.rag._chroma_client = None
        services.rag._chroma_collection = None

    @patch('services.rag.PdfReader')
    @patch('services.rag.httpx.AsyncClient')
    @patch('services.rag._get_chroma')
    async def test_add_pdf_document_success(self, mock_get_chroma, mock_httpx_client, mock_pdf_reader):
        # Mock PDF extraction
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is some text content for the PDF." * 10
        mock_pdf.pages = [mock_page]
        mock_pdf_reader.return_value = mock_pdf

        # Mock Embeddings API
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3], "index": 0}
            ]
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        # Mock ChromaDB
        mock_collection = MagicMock()
        mock_get_chroma.return_value = mock_collection

        # Run function
        user_id = 123
        pdf_bytes = b"fake pdf content"
        filename = "test.pdf"

        success, message = await services.rag.add_pdf_document(user_id, pdf_bytes, filename)

        self.assertTrue(success)
        self.assertIn("добавлен", message)

        # Verify calls
        mock_pdf_reader.assert_called_once()
        mock_collection.add.assert_called_once()

    @patch('services.rag.PdfReader')
    async def test_add_pdf_document_empty_text(self, mock_pdf_reader):
        # Mock PDF extraction returning empty
        mock_pdf = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdf.pages = [mock_page]
        mock_pdf_reader.return_value = mock_pdf

        success, message = await services.rag.add_pdf_document(123, b"content", "empty.pdf")

        self.assertFalse(success)
        self.assertIn("мало текста", message)

if __name__ == '__main__':
    unittest.main()
