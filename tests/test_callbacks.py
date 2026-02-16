"""
Тесты для handlers.callbacks: retry (перегенерация по callback_data).
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mocks import make_mock_context, setup_handler_mocks

setup_handler_mocks()
sys.modules["handlers.basic"] = MagicMock()
sys.modules["handlers.media"] = MagicMock()
sys.modules["handlers.payments"] = MagicMock()
sys.modules["handlers.conversation"] = MagicMock()
sys.modules["handlers.documents"] = MagicMock()
sys.modules["handlers.admin"] = MagicMock()

from handlers.callbacks import button_callback  # noqa: E402, I001


def _make_update_with_query(query):
    update = MagicMock()
    update.callback_query = query
    return update


@pytest.mark.asyncio
async def test_callback_retry_no_prompt():
    """Retry без промпта в user_data — answer с сообщением «Нет запроса»."""
    query = MagicMock()
    query.from_user = MagicMock(id=123)
    query.data = "retry_123_abc"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.delete = AsyncMock()
    query.message.reply_text = AsyncMock()
    query.message.edit_text = AsyncMock()
    context = make_mock_context(user_data={})
    update = _make_update_with_query(query)

    await button_callback(update, context)

    query.answer.assert_called_once()
    call_kw = query.answer.call_args[1]
    assert call_kw.get("show_alert") is True
    assert "Нет запроса" in str(call_kw.get("text", ""))


@pytest.mark.asyncio
async def test_callback_retry_calls_generate_and_reply():
    """Retry с промптом в user_data вызывает generate_and_reply_text и reply_text с ответом."""
    query = MagicMock()
    query.from_user = MagicMock(id=123)
    query.data = "retry_123_req1"
    query.answer = AsyncMock()
    query.message = MagicMock()
    query.message.chat = MagicMock()
    query.message.delete = AsyncMock()
    query.message.reply_text = AsyncMock()
    query.message.edit_text = AsyncMock()
    context = make_mock_context(
        user_data={"prompts": {"req1": "Original question"}, "last_prompt": "Original question"}
    )
    update = _make_update_with_query(query)

    mock_generate = AsyncMock(return_value="New response")
    mock_rag = AsyncMock(return_value=None)

    with (
        patch("handlers.chat.generate_and_reply_text", mock_generate),
        patch("services.rag.get_rag_context", mock_rag),
        patch("utils.text_tools.sanitize_markdown", lambda x: x),
    ):
        await button_callback(update, context)

    mock_generate.assert_called_once()
    call_kw = mock_generate.call_args[1]
    assert call_kw["prompt"] == "Original question"
    assert call_kw["user_id"] == 123
    query.message.reply_text.assert_called()
    # Финальный ответ с текстом
    reply_args = query.message.reply_text.call_args[0]
    assert "New response" in str(reply_args[0])
