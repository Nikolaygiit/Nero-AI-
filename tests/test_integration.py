"""
Интеграционный тест: сообщение → prepare_messages → cascade/gemini → ответ.
Моки только на границах: httpx, db.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Минимальные моки для загрузки config и database
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["sqlalchemy.ext.asyncio"] = MagicMock()
sys.modules["sqlalchemy.orm"] = MagicMock()
sys.modules["pydantic"] = MagicMock()
sys.modules["pydantic_settings"] = MagicMock()
sys.modules["redis"] = MagicMock()
sys.modules["structlog"] = MagicMock()

mock_db = MagicMock()
mock_db.get_user_messages = AsyncMock(return_value=[])
mock_db.get_user = AsyncMock(return_value=None)
mock_db.add_message = AsyncMock()
mock_db.update_stats = AsyncMock()
mock_db.create_or_update_user = AsyncMock()
sys.modules["database"] = MagicMock()
sys.modules["database.db"] = mock_db

mock_config = MagicMock()
mock_config.GEMINI_API_KEY = "test_key"
mock_config.GEMINI_API_BASE = "https://api.test/v1"
mock_config.PREFERRED_MODELS = ["model-a"]
mock_config.PERSONAS = {"assistant": {"prompt": "You are helpful."}}
mock_config.MAX_TOKENS_PER_REQUEST = 100
mock_config.MODEL_TIMEOUT_SEC = 10
mock_config.settings = MagicMock()
sys.modules["config"] = mock_config

sys.modules["services.memory"] = MagicMock()
sys.modules["services.memory"].get_relevant_facts = AsyncMock(return_value="")

# Импорт после моков (config уже замокан)
from services.gemini import GeminiService  # noqa: E402, I001


@pytest.mark.asyncio
async def test_flow_prepare_then_http_response():
    """
    Цепочка: _prepare_messages_context формирует сообщения,
    cascade (мок) возвращает ответ → generate_content возвращает текст.
    """
    service = GeminiService()
    messages = await service._prepare_messages_context(
        "What is 2+2?", user_id=None, use_context=False
    )
    assert len(messages) >= 1
    assert messages[0]["role"] == "system"
    assert any(m.get("content") == "What is 2+2?" for m in messages)

    # Вариант 1: cascade успешен (мок chat_completion)
    mock_chat = AsyncMock(return_value=("4", "artemox:model-a", 10))
    with (
        patch("services.llm_cascade.chat_completion", mock_chat),
        patch("services.gemini.db", mock_db),
    ):
        text = await service.generate_content("What is 2+2?", user_id=None, use_context=False)
    assert text.strip() == "4"
    mock_chat.assert_called_once()
    call_messages = mock_chat.call_args[1]["messages"]
    assert call_messages[-1]["content"] == "What is 2+2?"

    # Вариант 2: cascade падает → legacy fallback, мок httpx
    mock_chat_fail = AsyncMock(side_effect=RuntimeError("cascade down"))
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "42"}}],
        "usage": {"total_tokens": 5},
    }
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    with (
        patch("services.llm_cascade.chat_completion", mock_chat_fail),
        patch("services.gemini.httpx.AsyncClient", return_value=mock_client),
        patch("services.gemini.db", mock_db),
    ):
        text2 = await service.generate_content("Question", user_id=None, use_context=False)
    assert text2.strip() == "42"
