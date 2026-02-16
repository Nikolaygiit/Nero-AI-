
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


# Define exceptions that need to be available globally for the test
class MockTimeoutError(Exception):
    pass

class TestLLMCascadeRefactor(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Create mocks
        cls.mock_httpx = MagicMock()
        cls.mock_httpx.TimeoutException = MockTimeoutError
        cls.mock_httpx.HTTPError = Exception
        cls.mock_httpx.Limits = MagicMock()
        cls.mock_httpx.Timeout = MagicMock()

        cls.mock_config = MagicMock()
        cls.mock_config.MODEL_TIMEOUT_SEC = 10
        cls.mock_config.CIRCUIT_FAILURE_THRESHOLD = 3
        cls.mock_config.CIRCUIT_COOLDOWN_SEC = 60
        cls.mock_config.GEMINI_API_BASE = "https://api.artemox.com"
        cls.mock_config.GEMINI_API_KEY = "test_key"
        cls.mock_config.PREFERRED_MODELS = ["gemini-2.0-flash"]
        cls.mock_config.settings.DEEPSEEK_API_KEY = "deepseek_key"
        cls.mock_config.settings.OPENAI_API_KEY = "openai_key"

        # Apply patch.dict to sys.modules
        cls.modules_patcher = patch.dict(sys.modules, {
            "httpx": cls.mock_httpx,
            "config": cls.mock_config,
            "sqlalchemy": MagicMock(),
            "sqlalchemy.ext.asyncio": MagicMock(),
            "sqlalchemy.orm": MagicMock(),
            "database": MagicMock(),
            "services.gemini": MagicMock(),
            "services.image_gen": MagicMock(),
            "services.rag": MagicMock(),
            "services.memory": MagicMock(),
            "services.speech": MagicMock(),
            "google.generativeai": MagicMock(),
        })
        cls.modules_patcher.start()

        # Import the module under test *after* patching
        if "services.llm_cascade" in sys.modules:
            del sys.modules["services.llm_cascade"]
        import services.llm_cascade
        cls.llm_cascade = services.llm_cascade

    @classmethod
    def tearDownClass(cls):
        cls.modules_patcher.stop()

    async def asyncSetUp(self):
        self.provider = self.llm_cascade.LLMProvider(
            name="test_provider",
            api_base="https://api.test.com",
            api_key="test_key",
            models=["test_model"],
        )
        self.messages = [{"role": "user", "content": "hello"}]

        # Reset the mock client before each test
        self.mock_httpx.AsyncClient.reset_mock()

    async def test_sync_request_success(self):
        # Configure the mock client returned by httpx.AsyncClient()
        mock_client = AsyncMock()
        self.mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello world"}}],
            "usage": {"total_tokens": 10}
        }
        mock_client.post.return_value = mock_resp

        text, tokens, err = await self.llm_cascade._chat_completion_request(
            self.provider, "test_model", self.messages, stream=False
        )

        self.assertEqual(text, "Hello world")
        self.assertEqual(tokens, 10)
        self.assertIsNone(err)

    async def test_sync_request_failure(self):
        mock_client = AsyncMock()
        self.mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.content = b'{"error": {"message": "Internal Server Error"}}'
        mock_resp.json.return_value = {"error": {"message": "Internal Server Error"}}
        mock_client.post.return_value = mock_resp

        text, tokens, err = await self.llm_cascade._chat_completion_request(
            self.provider, "test_model", self.messages, stream=False
        )

        self.assertIsNone(text)
        self.assertIsNone(tokens)
        self.assertIsNotNone(err)
        self.assertIn("HTTP 500", str(err))

    async def test_stream_request_success(self):
        mock_client = AsyncMock()
        self.mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_stream_resp = MagicMock()
        mock_stream_resp.status_code = 200

        async def mock_aiter_lines():
            yield 'data: {"choices": [{"delta": {"content": "Hello"}}]}'
            yield 'data: {"choices": [{"delta": {"content": " world"}}]}'
            yield 'data: [DONE]'

        mock_stream_resp.aiter_lines = mock_aiter_lines

        # Configure stream to return an async context manager
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_ctx)

        text, tokens, err = await self.llm_cascade._chat_completion_request(
            self.provider, "test_model", self.messages, stream=True
        )

        self.assertEqual(text, "Hello world")
        self.assertIsNone(tokens)
        self.assertIsNone(err)

    async def test_stream_request_failure(self):
        mock_client = AsyncMock()
        self.mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_stream_resp = MagicMock()
        mock_stream_resp.status_code = 400
        mock_stream_resp.aread = AsyncMock(return_value=b"Bad Request")

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_ctx)

        text, tokens, err = await self.llm_cascade._chat_completion_request(
            self.provider, "test_model", self.messages, stream=True
        )

        self.assertIsNone(text)
        self.assertIsNotNone(err)
        self.assertIn("HTTP 400", str(err))
