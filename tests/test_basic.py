import asyncio
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

# Add project root to path
sys.path.append(os.getcwd())

# Mock external dependencies
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["sqlalchemy.ext.asyncio"] = MagicMock()
sys.modules["sqlalchemy.orm"] = MagicMock()
sys.modules["httpx"] = MagicMock()
sys.modules["pydantic"] = MagicMock()
sys.modules["pydantic_settings"] = MagicMock()
sys.modules["telegram"] = MagicMock()
sys.modules["telegram.ext"] = MagicMock()
sys.modules["redis"] = MagicMock()
sys.modules["structlog"] = MagicMock()

# Configure database mocks
mock_db_module = MagicMock()
mock_db_instance = MagicMock()
mock_db_module.db = mock_db_instance
sys.modules["database"] = mock_db_module
sys.modules["database.db"] = mock_db_module

# Configure config mocks
mock_config = MagicMock()
mock_config.GEMINI_API_KEY = "test_key"
mock_config.GEMINI_API_BASE = "http://test.base"
mock_config.PREFERRED_MODELS = ["model-a"]
mock_config.PERSONAS = {"assistant": {"prompt": "You are helpful."}}
mock_config.MAX_TOKENS_PER_REQUEST = 100
sys.modules["config"] = mock_config

# Import services after mocking
sys.modules["services.image_gen"] = MagicMock()

# Now we can safely import GeminiService
if "services.gemini" in sys.modules:
    del sys.modules["services.gemini"]
# ruff: noqa: E402
from services.gemini import GeminiService


class TestGeminiService(unittest.TestCase):
    def setUp(self):
        # Reset mocks before each test
        mock_db_instance.reset_mock()
        mock_config.reset_mock()

    def test_init(self):
        service = GeminiService()
        self.assertEqual(service.api_key, "test_key")

    def test_list_available_models(self):
        async def run_test():
            service = GeminiService()

            # Setup HTTPX mock properly
            mock_httpx = sys.modules["httpx"]
            mock_client_instance = AsyncMock()
            mock_httpx.AsyncClient.return_value = mock_client_instance

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"data": [{"id": "model-x"}, {"id": "model-y"}]}
            mock_response.raise_for_status = MagicMock()

            # Async context manager mock
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            mock_client_instance.get.return_value = mock_response

            # Clear cache
            import services.gemini

            services.gemini.available_models_cache = []

            models = await service.list_available_models()
            self.assertEqual(models, ["model-x", "model-y"])
            mock_client_instance.get.assert_called_once()

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
