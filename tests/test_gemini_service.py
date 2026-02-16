"""
Unit-тесты для services.gemini: _prepare_messages_context, _prepare_vision_messages,
_parse_stream_delta, _execute_vision_request (с моками db/httpx).
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Моки до импорта сервисов
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["sqlalchemy.ext.asyncio"] = MagicMock()
sys.modules["sqlalchemy.orm"] = MagicMock()
sys.modules["pydantic"] = MagicMock()
sys.modules["pydantic_settings"] = MagicMock()
sys.modules["telegram"] = MagicMock()
sys.modules["telegram.ext"] = MagicMock()
sys.modules["redis"] = MagicMock()
sys.modules["structlog"] = MagicMock()

mock_db = MagicMock()
sys.modules["database"] = MagicMock()
sys.modules["database.db"] = mock_db

mock_config = MagicMock()
mock_config.GEMINI_API_KEY = "key"
mock_config.GEMINI_API_BASE = "https://api.test/v1"
mock_config.PREFERRED_MODELS = ["model-a"]
mock_config.PERSONAS = {"assistant": {"prompt": "You are helpful."}}
mock_config.MAX_TOKENS_PER_REQUEST = 100
mock_config.MAX_CONTEXT_CHARS = 5000
sys.modules["config"] = mock_config
sys.modules["config.settings"] = MagicMock()

sys.modules["services.image_gen"] = MagicMock()

# Мок memory.get_relevant_facts
mock_memory = MagicMock()
mock_memory.get_relevant_facts = AsyncMock(return_value="")
sys.modules["services.memory"] = mock_memory

if "services.gemini" in sys.modules:
    del sys.modules["services.gemini"]
from services.gemini import GeminiService  # noqa: E402, I001


# --- _parse_stream_delta (синхронный, без зависимостей) ---


class TestParseStreamDelta:
    def test_returns_delta_content(self):
        service = GeminiService()
        line = 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
        assert service._parse_stream_delta(line) == "Hello"

    def test_returns_empty_for_done(self):
        service = GeminiService()
        assert service._parse_stream_delta("data: [DONE]") == ""

    def test_returns_empty_for_non_data_line(self):
        service = GeminiService()
        assert service._parse_stream_delta(": keep-alive") == ""

    def test_returns_empty_on_invalid_json(self):
        service = GeminiService()
        assert service._parse_stream_delta("data: not json") == ""


# --- _prepare_messages_context (async, моки db + memory) ---


@pytest.mark.asyncio
async def test_prepare_messages_context_no_user():
    """Без user_id не вызываются db и get_relevant_facts."""
    service = GeminiService()
    messages = await service._prepare_messages_context("Hello", user_id=None, use_context=False)
    assert len(messages) >= 1
    assert messages[0]["role"] == "system"
    assert "Важно" in messages[0]["content"] or "русском" in messages[0]["content"]
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Hello"


@pytest.mark.asyncio
async def test_prepare_messages_context_with_user_mocked():
    mock_db.get_user_messages = AsyncMock(return_value=[])
    mock_db.get_user = AsyncMock(return_value=MagicMock(persona="assistant"))
    with (
        patch("services.gemini.db", mock_db),
        patch("services.memory.get_relevant_facts", new_callable=AsyncMock, return_value=""),
    ):
        service = GeminiService()
        messages = await service._prepare_messages_context("Hi", user_id=123, use_context=True)
    assert messages[0]["role"] == "system"
    assert messages[-1]["content"] == "Hi"


@pytest.mark.asyncio
async def test_prepare_messages_context_basic():
    """RAG-контекст попадает в системное сообщение."""
    service = GeminiService()
    messages = await service._prepare_messages_context(
        "Test prompt", user_id=None, use_context=False, rag_context="RAG text"
    )
    assert any(m.get("role") == "system" for m in messages)
    assert any(m.get("content") == "Test prompt" for m in messages)
    system_msg = next(m for m in messages if m.get("role") == "system")
    assert "RAG text" in system_msg["content"]


@pytest.mark.asyncio
async def test_prepare_messages_context_trims_by_max_chars():
    """История обрезается по MAX_CONTEXT_CHARS (старые сообщения убираются)."""
    long = "x" * 2000  # 2000 символов на сообщение
    mock_db.get_user_messages = AsyncMock(
        return_value=[
            MagicMock(role="user", content=long),
            MagicMock(role="assistant", content=long),
            MagicMock(role="user", content=long),
            MagicMock(role="assistant", content=long),
        ]
    )
    mock_db.get_user = AsyncMock(return_value=MagicMock(persona="assistant"))
    with (
        patch("services.gemini.db", mock_db),
        patch("services.memory.get_relevant_facts", new_callable=AsyncMock, return_value=""),
    ):
        service = GeminiService()
        messages = await service._prepare_messages_context(
            "Hi", user_id=1, use_context=True, history_limit=10
        )
    # Системное + контекст (должен быть обрезан до <= 5000) + пользовательское "Hi"
    context_msgs = [
        m for m in messages if m.get("role") in ("user", "assistant") and m.get("content") != "Hi"
    ]
    total_context = sum(len(m.get("content", "") or "") for m in context_msgs)
    assert total_context <= 5000, "Контекст должен быть обрезан до MAX_CONTEXT_CHARS"
    assert "Hi" in [m.get("content") for m in messages]


# --- _prepare_vision_messages (без контекста — только user с картинкой) ---


@pytest.mark.asyncio
async def test_prepare_vision_messages_no_context():
    service = GeminiService()
    messages = await service._prepare_vision_messages(
        "Describe this", "base64fake", user_id=None, use_context=False
    )
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert any(p.get("type") == "text" and p.get("text") == "Describe this" for p in content)
    assert any(p.get("type") == "image_url" for p in content)


# --- _execute_vision_request (мок httpx) ---


@pytest.mark.asyncio
async def test_execute_vision_request_success():
    service = GeminiService()
    messages = [{"role": "user", "content": [{"type": "text", "text": "What is this?"}]}]
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "This is a test image."}}]
    }

    async def fake_post(*args, **kwargs):
        return mock_response

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=fake_post)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.gemini.httpx.AsyncClient", return_value=mock_client):
        result = await service._execute_vision_request(
            messages, user_id=None, prompt_for_db="What is this?"
        )
    assert result == "This is a test image."


@pytest.mark.asyncio
async def test_execute_vision_request_empty_when_all_fail():
    service = GeminiService()
    messages = [{"role": "user", "content": [{"type": "text", "text": "?"}]}]
    mock_response = MagicMock()
    mock_response.status_code = 500

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.gemini.httpx.AsyncClient", return_value=mock_client):
        result = await service._execute_vision_request(messages, user_id=None, prompt_for_db="?")
    assert result == ""
