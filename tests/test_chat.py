"""
Тесты для handlers.chat: handle_message (стриминг, fallback, картинка, мультимодальный ответ).
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.mocks import (
    make_mock_context,
    make_mock_update,
    setup_handler_mocks,
)

# Моки до импорта chat
setup_handler_mocks()

# Доп. моки для chat (image_gen, taskiq, get_rag_context)
sys.modules["handlers.basic"] = MagicMock()
sys.modules["handlers.callbacks"] = MagicMock()
sys.modules["handlers.payments"] = MagicMock()
sys.modules["handlers.conversation"] = MagicMock()
sys.modules["handlers.documents"] = MagicMock()
sys.modules["handlers.media"] = MagicMock()
sys.modules["handlers.admin"] = MagicMock()

from handlers.chat import (  # noqa: E402, I001
    generate_and_reply_text,
    handle_message,
)


@pytest.mark.asyncio
async def test_generate_and_reply_text_stream():
    """generate_and_reply_text при успешном стриме накапливает чанки и возвращает полный текст."""
    mock_stream = AsyncMock(return_value=MagicMock())
    mock_stream.__aiter__ = lambda self: self
    mock_stream.__anext__ = AsyncMock(side_effect=[("Hello",), (" world",), StopAsyncIteration])

    # Реализуем как async generator
    async def gen():
        yield "Hello"
        yield " world"

    mock_gemini = MagicMock()
    mock_gemini.generate_content_stream = lambda **kw: gen()
    mock_gemini.generate_content = AsyncMock()

    with (
        patch("handlers.chat.gemini_service", mock_gemini),
        patch("handlers.chat.db", MagicMock(add_message=AsyncMock())),
    ):
        result = await generate_and_reply_text(
            MagicMock(), user_id=1, prompt="Hi", context=MagicMock(), rag_context=None
        )
    assert result == "Hello world"


@pytest.mark.asyncio
async def test_generate_and_reply_text_fallback_on_stream_error():
    """При ошибке стрима вызывается generate_content (fallback)."""
    mock_gemini = MagicMock()

    async def stream_raise_gen(**kw):
        raise RuntimeError("stream failed")
        yield  # unreachable — делаем async generator, чтобы async for не получал не-awaited coroutine

    mock_gemini.generate_content_stream = stream_raise_gen
    mock_gemini.generate_content = AsyncMock(return_value="Fallback reply")

    with patch("handlers.chat.gemini_service", mock_gemini):
        result = await generate_and_reply_text(
            MagicMock(), user_id=1, prompt="Hi", context=MagicMock(), rag_context=None
        )
    assert result == "Fallback reply"
    mock_gemini.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_handle_message_banned():
    """Если пользователь забанен — сразу ответ и return."""
    mock_db = MagicMock()
    mock_db.is_banned = AsyncMock(return_value=True)
    update = make_mock_update(user_id=999, text="Hi")
    context = make_mock_context()

    with patch("handlers.chat.db", mock_db):
        await handle_message(update, context)
    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "заблокированы" in call_text.lower() or "заблокирован" in call_text.lower()


@pytest.mark.asyncio
async def test_handle_message_rate_limit():
    """При превышении rate limit — ответ с сообщением о лимите."""
    mock_db = MagicMock()
    mock_db.is_banned = AsyncMock(return_value=False)
    mock_rate = MagicMock()
    mock_rate.check_rate_limit = AsyncMock(return_value=False)
    mock_rate.time_window = 60
    mock_rate.max_requests = 30
    update = make_mock_update(text="Hello")
    context = make_mock_context()

    with (
        patch("handlers.chat.db", mock_db),
        patch("handlers.chat.rate_limit_middleware", mock_rate),
        patch("handlers.chat.extract_and_save_facts", AsyncMock()),
    ):
        await handle_message(update, context)
    update.message.reply_text.assert_called_once()
    call_text = update.message.reply_text.call_args[0][0]
    assert "лимит" in call_text.lower() or "подождит" in call_text.lower() or "секунд" in call_text


@pytest.mark.asyncio
async def test_handle_message_usage_limit():
    """При исчерпании дневного лимита — ответ limit_msg."""
    mock_db = MagicMock()
    mock_db.is_banned = AsyncMock(return_value=False)
    mock_check = AsyncMock(return_value=(False, "Лимит исчерпан"))
    update = make_mock_update(text="Hi")
    context = make_mock_context()

    with (
        patch("handlers.chat.db", mock_db),
        patch(
            "handlers.chat.rate_limit_middleware",
            MagicMock(check_rate_limit=AsyncMock(return_value=True)),
        ),
        patch("handlers.chat.extract_and_save_facts", AsyncMock()),
        patch("handlers.chat.check_can_make_request", mock_check),
    ):
        await handle_message(update, context)
    update.message.reply_text.assert_called_once()
    assert "Лимит" in update.message.reply_text.call_args[0][0]


@pytest.mark.asyncio
async def test_handle_message_stream_then_reply():
    """Обычное сообщение: стрим, get_rag_context, финальный reply_text."""
    mock_db = MagicMock()
    mock_db.is_banned = AsyncMock(return_value=False)
    mock_db.increment_daily_usage = AsyncMock()

    async def stream_gen(**kw):
        yield "Answer"
        yield " text"

    mock_gemini = MagicMock()
    mock_gemini.generate_content_stream = stream_gen
    mock_gemini.generate_content = AsyncMock()
    mock_rag = AsyncMock(return_value=None)
    update = make_mock_update(text="What is Python?")
    context = make_mock_context()

    with (
        patch("handlers.chat.db", mock_db),
        patch(
            "handlers.chat.rate_limit_middleware",
            MagicMock(check_rate_limit=AsyncMock(return_value=True)),
        ),
        patch("handlers.chat.check_can_make_request", AsyncMock(return_value=(True, ""))),
        patch("handlers.chat.extract_and_save_facts", AsyncMock()),
        patch("handlers.chat.get_rag_context", mock_rag),
        patch("handlers.chat.gemini_service", mock_gemini),
        patch("handlers.chat.track", MagicMock()),
        patch("handlers.chat.sanitize_markdown", lambda x: x),
    ):
        await handle_message(update, context)

    # Должны быть: reply_text("thinking"), затем reply_text с финальным ответом
    assert update.message.reply_text.call_count >= 2
    reply_calls = [c[0][0] for c in update.message.reply_text.call_args_list]
    # Один из вызовов — финальный ответ со стримленным текстом
    full_reply = " ".join(str(r) for r in reply_calls)
    assert "Answer" in full_reply and "text" in full_reply
