import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

# Configure sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock external libs
sys.modules['telegram'] = MagicMock()
sys.modules['telegram.ext'] = MagicMock()
sys.modules['telegram.error'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['sqlalchemy'] = MagicMock()
sys.modules['sqlalchemy.ext.asyncio'] = MagicMock()
sys.modules['structlog'] = MagicMock()
sys.modules['pydantic'] = MagicMock()

# Mock internal modules
mock_db_module = MagicMock()
mock_db_obj = AsyncMock()
mock_db_obj.is_banned.return_value = False
mock_db_obj.increment_daily_usage.return_value = None
mock_db_module.db = mock_db_obj
sys.modules['database'] = mock_db_module

mock_gemini_module = MagicMock()
mock_gemini_service = AsyncMock()
mock_gemini_module.gemini_service = mock_gemini_service
sys.modules['services.gemini'] = mock_gemini_module

sys.modules['services.image_gen'] = MagicMock()
sys.modules['tasks.image_tasks'] = MagicMock()
sys.modules['tasks.broker'] = MagicMock()

mock_rate_limit_module = MagicMock()
mock_rate_limit_obj = AsyncMock()
mock_rate_limit_obj.check_rate_limit.return_value = True
mock_rate_limit_module.rate_limit_middleware = mock_rate_limit_obj
sys.modules['middlewares.rate_limit'] = mock_rate_limit_module

mock_usage_limit_module = MagicMock()
mock_usage_limit_module.check_can_make_request = AsyncMock(return_value=(True, ""))
sys.modules['middlewares.usage_limit'] = mock_usage_limit_module

mock_text_tools = MagicMock()
mock_text_tools.sanitize_markdown = lambda x: x
sys.modules['utils.text_tools'] = mock_text_tools

sys.modules['utils.analytics'] = MagicMock()

# i18n
mock_i18n = MagicMock()
mock_i18n.t.return_value = "Thinking..."
sys.modules['utils.i18n'] = mock_i18n

sys.modules['services.memory'] = MagicMock()
sys.modules['services.memory'].extract_and_save_facts = AsyncMock()
sys.modules['services.rag'] = MagicMock()
sys.modules['services.rag'].get_rag_context = AsyncMock(return_value="")

sys.modules['services.speech'] = MagicMock()
sys.modules['config'] = MagicMock()

import pytest
from handlers.chat import handle_message

async def run_chat_stream_optimization():
    """Test the streaming loop optimization in handle_message"""

    # Mock dependencies
    mock_update = MagicMock()
    mock_context = MagicMock()
    mock_user = MagicMock()
    mock_user.id = 12345
    mock_update.effective_user = mock_user
    mock_update.message.text = "Hello bot"
    mock_update.effective_chat.id = 67890

    # Mock status message
    mock_status_msg = AsyncMock()
    # reply_text is awaited, so it should be AsyncMock or MagicMock returning awaitable
    mock_update.message.reply_text = AsyncMock(return_value=mock_status_msg)
    mock_update.message.reply_chat_action = AsyncMock()

    # Mock context user_data
    mock_context.user_data = {}

    # Define the stream behavior
    async def mock_stream_gen(**kwargs):
        chunks = ["Hello", " ", "world", "!", " This", " is", " a", " test."]
        for chunk in chunks:
            yield chunk

    # Setup the mock service to use our generator
    # generate_content_stream is NOT awaited directly, it is used in `async for`.
    # So it should be a MagicMock that returns the async generator object when called.
    mock_gemini_service.generate_content_stream = MagicMock(side_effect=mock_stream_gen)

    # Run handle_message
    await handle_message(mock_update, mock_context)

    # Verify gemini service called
    mock_gemini_service.generate_content_stream.assert_called_once()

    # Verify final output in calls
    expected_text = "Hello world! This is a test."

    calls = mock_update.message.reply_text.call_args_list
    found = False
    for call in calls:
        args, _ = call
        if args and expected_text in str(args[0]):
            found = True
            break

    assert found, f"Expected final reply '{expected_text}' not found in calls: {calls}"

def test_chat_stream_optimization():
    asyncio.run(run_chat_stream_optimization())

if __name__ == '__main__':
    test_chat_stream_optimization()
