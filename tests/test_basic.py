"""
Базовые тесты для бота
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from database import db
from services.gemini import GeminiService

# Используем тестовую базу данных
TEST_DB_PATH = 'test_bot_database.db'

@pytest.fixture
async def setup_db():
    print("SETUP DB STARTED")
    # Настройка: меняем путь к БД на тестовый
    db.db_path = TEST_DB_PATH
    # Удаляем старую БД если есть
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

    # Инициализируем БД заново
    await db.init()
    print(f"DB INITIALIZED. Engine: {db.engine}")

    yield db

    print("TEARDOWN DB")
    # Очистка: закрываем соединение и удаляем файл
    await db.close()
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except OSError:
            pass

@pytest.mark.asyncio
async def test_database_init(setup_db):
    """Тест инициализации базы данных"""
    print(f"TEST DB INIT. Engine: {db.engine}")
    assert db.engine is not None
    assert db.async_session is not None

@pytest.mark.asyncio
async def test_create_user(setup_db):
    """Тест создания пользователя"""
    user = await db.create_or_update_user(
        telegram_id=12345,
        username="test_user",
        first_name="Test"
    )

    assert user is not None
    assert user.telegram_id == 12345
    assert user.username == "test_user"

    # Проверяем получение пользователя
    retrieved_user = await db.get_user(12345)
    assert retrieved_user is not None
    assert retrieved_user.telegram_id == 12345

@pytest.mark.asyncio
async def test_add_message(setup_db):
    """Тест добавления сообщения"""
    # Создаем пользователя
    await db.create_or_update_user(telegram_id=12345)

    # Добавляем сообщение
    await db.add_message(12345, "user", "Привет!")
    await db.add_message(12345, "assistant", "Привет! Как дела?")

    # Получаем сообщения
    messages = await db.get_user_messages(12345, limit=10)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "Привет!"
    assert messages[1].role == "assistant"

@pytest.mark.asyncio
async def test_update_stats(setup_db):
    """Тест обновления статистики"""
    # Создаем пользователя
    await db.create_or_update_user(telegram_id=12345)

    # Обновляем статистику
    await db.update_stats(12345, requests_count=1, tokens_used=100)
    await db.update_stats(12345, command='start')

    # Проверяем статистику
    stats = await db.get_stats(12345)
    assert stats is not None
    assert stats.requests_count == 1
    assert stats.tokens_used == 100
    assert stats.commands_used.get('start') == 1

@pytest.mark.asyncio
async def test_gemini_service_list_models():
    """Тест получения списка моделей"""
    with patch('httpx.AsyncClient') as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'data': [
                {'id': 'gemini-2.0-flash'},
                {'id': 'gemini-3-pro-preview'}
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None
        mock_client_instance.get.return_value = mock_response
        mock_client.return_value = mock_client_instance

        async with GeminiService() as service:
            models = await service.list_available_models()
            assert len(models) > 0

@pytest.mark.asyncio
async def test_rate_limit_middleware():
    """Тест rate limiting middleware"""
    from middlewares.rate_limit import RateLimitMiddleware

    middleware = RateLimitMiddleware(max_requests=2, time_window=60)

    # Первые два запроса должны пройти
    assert await middleware.check_rate_limit(12345) is True
    assert await middleware.check_rate_limit(12345) is True

    # Третий запрос должен быть заблокирован
    assert await middleware.check_rate_limit(12345) is False

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
