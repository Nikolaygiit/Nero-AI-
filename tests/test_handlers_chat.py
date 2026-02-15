import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Message, Chat
from handlers.chat import handle_message
from handlers.chat_utils import is_image_request, get_image_prompt

@pytest.fixture
def mock_update():
    update = MagicMock(spec=Update)
    update.effective_user = MagicMock(spec=User)
    update.effective_user.id = 12345
    update.effective_chat = MagicMock(spec=Chat)
    update.effective_chat.id = 67890
    update.message = MagicMock(spec=Message)
    update.message.text = "Hello world"
    update.message.reply_text = AsyncMock()
    update.message.reply_chat_action = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {}
    return context

@pytest.fixture
async def mock_db():
    with patch('database.db.db') as mock_db_instance:
        mock_db_instance.async_session = MagicMock()
        mock_db_instance.async_session.return_value.__aenter__.return_value = AsyncMock()
        mock_db_instance.is_premium = AsyncMock(return_value=False)
        mock_db_instance.get_daily_usage = AsyncMock(return_value=0)
        yield mock_db_instance

@pytest.mark.asyncio
async def test_is_image_request():
    assert is_image_request("создай картинку кот") == True
    assert is_image_request("нарисуй пейзаж") == True
    assert is_image_request("привет, как дела?") == False

@pytest.mark.asyncio
async def test_get_image_prompt():
    # Простой случай
    assert get_image_prompt("создай картинку кот") == "кот"
    # Случай с запятой
    assert get_image_prompt("нарисуй, пейзаж") == "пейзаж"
    # Случай без изменений
    assert get_image_prompt("просто текст") == "просто текст"

@pytest.mark.asyncio
async def test_handle_message_banned_user(mock_update, mock_context):
    with patch('database.db.Database.is_banned', new_callable=AsyncMock) as mock_is_banned:
        mock_is_banned.return_value = True

        await handle_message(mock_update, mock_context)

        mock_update.message.reply_text.assert_called_with("⛔ Вы заблокированы и не можете использовать бота.")

@pytest.mark.asyncio
async def test_handle_message_rate_limit(mock_update, mock_context):
    with patch('database.db.Database.is_banned', new_callable=AsyncMock) as mock_is_banned, \
         patch('middlewares.rate_limit.rate_limit_middleware.check_rate_limit', new_callable=AsyncMock) as mock_check_rate_limit:

        mock_is_banned.return_value = False
        mock_check_rate_limit.return_value = False

        await handle_message(mock_update, mock_context)

        # Verify rate limit message was sent
        args, _ = mock_update.message.reply_text.call_args
        assert "Лимит" in args[0]

@pytest.mark.asyncio
async def test_handle_message_image_request(mock_update, mock_context):
    mock_update.message.text = "создай картинку тест"

    with patch('database.db.Database.is_banned', new_callable=AsyncMock) as mock_is_banned, \
         patch('middlewares.rate_limit.rate_limit_middleware.check_rate_limit', new_callable=AsyncMock) as mock_check_rate_limit, \
         patch('middlewares.usage_limit.check_can_make_request', new_callable=AsyncMock) as mock_check_usage, \
         patch('handlers.chat.handle_image_generation', new_callable=AsyncMock) as mock_handle_image, \
         patch('database.db.Database.is_premium', new_callable=AsyncMock) as mock_is_premium, \
         patch('database.db.Database.get_daily_usage', new_callable=AsyncMock) as mock_get_daily_usage:

        mock_is_banned.return_value = False
        mock_check_rate_limit.return_value = True
        mock_check_usage.return_value = (True, "")
        mock_is_premium.return_value = False
        mock_get_daily_usage.return_value = 0

        await handle_message(mock_update, mock_context)

        mock_handle_image.assert_called_once()

@pytest.mark.asyncio
async def test_handle_message_text_flow(mock_update, mock_context):
    with patch('database.db.Database.is_banned', new_callable=AsyncMock) as mock_is_banned, \
         patch('middlewares.rate_limit.rate_limit_middleware.check_rate_limit', new_callable=AsyncMock) as mock_check_rate_limit, \
         patch('middlewares.usage_limit.check_can_make_request', new_callable=AsyncMock) as mock_check_usage, \
         patch('handlers.chat.extract_and_save_facts', new_callable=AsyncMock), \
         patch('handlers.chat.get_rag_context', new_callable=AsyncMock) as mock_rag, \
         patch('handlers.chat.stream_text_response', new_callable=AsyncMock) as mock_stream, \
         patch('handlers.chat.send_response_parts', new_callable=AsyncMock) as mock_send_parts, \
         patch('database.db.Database.increment_daily_usage', new_callable=AsyncMock), \
         patch('database.db.Database.is_premium', new_callable=AsyncMock) as mock_is_premium, \
         patch('database.db.Database.get_daily_usage', new_callable=AsyncMock) as mock_get_daily_usage:

        mock_is_banned.return_value = False
        mock_check_rate_limit.return_value = True
        mock_check_usage.return_value = (True, "")
        mock_rag.return_value = "some context"
        mock_stream.return_value = "generated response"
        mock_is_premium.return_value = False
        mock_get_daily_usage.return_value = 0

        await handle_message(mock_update, mock_context)

        mock_stream.assert_called_once()
        mock_send_parts.assert_called_once()
