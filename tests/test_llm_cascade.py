import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# 1. Mock dependencies
mock_httpx = MagicMock()
sys.modules["httpx"] = mock_httpx

# Define exceptions on the mock so they can be caught
class MockTimeoutException(Exception): pass
mock_httpx.TimeoutException = MockTimeoutException
mock_httpx.HTTPError = Exception
mock_httpx.Limits = MagicMock()
mock_httpx.Timeout = MagicMock()

# Mock config
mock_config = MagicMock()
mock_config.MODEL_TIMEOUT_SEC = 10
mock_config.CIRCUIT_FAILURE_THRESHOLD = 3
mock_config.CIRCUIT_COOLDOWN_SEC = 60
mock_config.GEMINI_API_BASE = "https://api.artemox.com"
mock_config.GEMINI_API_KEY = "test_key"
mock_config.PREFERRED_MODELS = ["gemini-2.0-flash"]
mock_config.settings.DEEPSEEK_API_KEY = "deepseek_key"
mock_config.settings.OPENAI_API_KEY = "openai_key"
sys.modules["config"] = mock_config

# Mock sqlalchemy
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["sqlalchemy.ext.asyncio"] = MagicMock()
sys.modules["sqlalchemy.orm"] = MagicMock()

# Mock database
sys.modules["database"] = MagicMock()

# Mock sibling services and other dependencies to prevent deep imports
sys.modules["services.gemini"] = MagicMock()
sys.modules["services.image_gen"] = MagicMock()
sys.modules["services.rag"] = MagicMock()
sys.modules["services.memory"] = MagicMock()
sys.modules["services.speech"] = MagicMock()
sys.modules["google.generativeai"] = MagicMock()

# 2. Import target module
from services.llm_cascade import _chat_completion_request, LLMProvider

import pytest

@pytest.mark.asyncio
class TestLLMCascadeRefactor(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.provider = LLMProvider(
            name="test_provider",
            api_base="https://api.test.com",
            api_key="test_key",
            models=["test_model"],
        )
        self.messages = [{"role": "user", "content": "hello"}]

        # Reset the mock client before each test
        mock_httpx.AsyncClient.reset_mock()

    async def test_sync_request_success(self):
        # Configure the mock client returned by httpx.AsyncClient()
        mock_client = AsyncMock()
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello world"}}],
            "usage": {"total_tokens": 10}
        }
        mock_client.post.return_value = mock_resp

        text, tokens, err = await _chat_completion_request(
            self.provider, "test_model", self.messages, stream=False
        )

        self.assertEqual(text, "Hello world")
        self.assertEqual(tokens, 10)
        self.assertIsNone(err)

    async def test_sync_request_failure(self):
        mock_client = AsyncMock()
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.content = b'{"error": {"message": "Internal Server Error"}}'
        mock_resp.json.return_value = {"error": {"message": "Internal Server Error"}}
        mock_client.post.return_value = mock_resp

        text, tokens, err = await _chat_completion_request(
            self.provider, "test_model", self.messages, stream=False
        )

        self.assertIsNone(text)
        self.assertIsNone(tokens)
        self.assertIsNotNone(err)
        self.assertIn("HTTP 500", str(err))

    async def test_stream_request_success(self):
        mock_client = AsyncMock()
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

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

        text, tokens, err = await _chat_completion_request(
            self.provider, "test_model", self.messages, stream=True
        )

        self.assertEqual(text, "Hello world")
        self.assertIsNone(tokens)
        self.assertIsNone(err)

    async def test_stream_request_failure(self):
        mock_client = AsyncMock()
        mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

        mock_stream_resp = MagicMock()
        mock_stream_resp.status_code = 400
        mock_stream_resp.aread = AsyncMock(return_value=b"Bad Request")

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream = MagicMock(return_value=mock_ctx)

        text, tokens, err = await _chat_completion_request(
            self.provider, "test_model", self.messages, stream=True
        )

        self.assertIsNone(text)
        self.assertIsNotNone(err)
        self.assertIn("HTTP 400", str(err))
