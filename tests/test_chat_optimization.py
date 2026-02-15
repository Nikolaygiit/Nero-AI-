import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Configure sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


async def run_chat_stream_optimization():
    """Test the streaming loop optimization in handle_message"""

    # Create mock modules to inject into sys.modules
    mock_db = MagicMock()
    mock_db.db = AsyncMock()
    mock_db.db.is_banned.return_value = False
    mock_db.db.increment_daily_usage.return_value = None

    mock_gemini = MagicMock()
    mock_gemini_service = AsyncMock()
    mock_gemini.gemini_service = mock_gemini_service

    # Define the stream behavior
    async def mock_stream_gen(**kwargs):
        chunks = ["Hello", " ", "world", "!", " This", " is", " a", " test."]
        for chunk in chunks:
            yield chunk

    # Mock the method that returns the async generator
    mock_gemini_service.generate_content_stream = MagicMock(side_effect=mock_stream_gen)

    # Mock other dependencies
    mocks = {
        "database": mock_db,
        "services.gemini": mock_gemini,
        "services.image_gen": MagicMock(),
        "tasks.image_tasks": MagicMock(),
        "tasks.broker": MagicMock(),
        "middlewares.rate_limit": MagicMock(),
        "middlewares.usage_limit": MagicMock(),
        "utils.text_tools": MagicMock(),
        "utils.analytics": MagicMock(),
        "utils.i18n": MagicMock(),
        "services.memory": MagicMock(),
        "services.rag": MagicMock(),
        "services.speech": MagicMock(),
        "config": MagicMock(),
        "telegram": MagicMock(),
        "telegram.ext": MagicMock(),
        "telegram.error": MagicMock(),
        "structlog": MagicMock(),
        "httpx": MagicMock(),
        "sqlalchemy": MagicMock(),
        "sqlalchemy.ext.asyncio": MagicMock(),
        "pydantic": MagicMock(),
    }

    mocks["middlewares.rate_limit"].rate_limit_middleware.check_rate_limit = AsyncMock(
        return_value=True
    )
    mocks["middlewares.usage_limit"].check_can_make_request = AsyncMock(return_value=(True, ""))
    mocks["utils.text_tools"].sanitize_markdown = lambda x: x
    mocks["utils.i18n"].t.return_value = "Thinking..."
    mocks["services.memory"].extract_and_save_facts = AsyncMock()
    mocks["services.rag"].get_rag_context = AsyncMock(return_value="")

    # Apply patches safely
    with patch.dict(sys.modules, mocks):
        if "handlers.chat" in sys.modules:
            del sys.modules["handlers.chat"]

        from handlers.chat import handle_message

        mock_update = MagicMock()
        mock_context = MagicMock()
        mock_user = MagicMock()
        mock_user.id = 12345
        mock_update.effective_user = mock_user
        mock_update.message.text = "Hello bot"
        mock_update.effective_chat.id = 67890

        mock_status_msg = AsyncMock()
        mock_update.message.reply_text = AsyncMock(return_value=mock_status_msg)
        mock_update.message.reply_chat_action = AsyncMock()
        mock_context.user_data = {}

        await handle_message(mock_update, mock_context)

        mock_gemini_service.generate_content_stream.assert_called_once()

        expected_text = "Hello world! This is a test."

        calls = mock_update.message.reply_text.call_args_list
        found = False
        for call in calls:
            args, _ = call
            if args and expected_text in str(args[0]):
                found = True
                break

        if not found:
            edit_calls = mock_status_msg.edit_text.call_args_list
            for call in edit_calls:
                args, _ = call
                if args and expected_text in str(args[0]):
                    found = True
                    break

        assert found, f"Expected final reply '{expected_text}' not found. Reply calls: {calls}"


def test_chat_stream_optimization():
    asyncio.run(run_chat_stream_optimization())


if __name__ == "__main__":
    test_chat_stream_optimization()
