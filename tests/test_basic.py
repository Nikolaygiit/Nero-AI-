"""
Базовые тесты для бота (unittest version)
"""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock sys.modules for missing dependencies if necessary,
# but here it seems the environment has sqlalchemy/httpx or we assume it does for the check.
# If dependencies are missing, the imports will fail.
# Given previous errors were only about pytest_asyncio, assume others are present.
from database import db
from services.gemini import GeminiService


class TestBasic(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        """Настройка перед каждым тестом"""
        db.db_path = ':memory:'
        await db.init()

    async def asyncTearDown(self):
        """Очистка после каждого теста"""
        await db.close()

    async def test_database_init(self):
        """Тест инициализации базы данных"""
        assert db.engine is not None
        assert db.async_session is not None

    async def test_create_user(self):
        """Тест создания пользователя"""
        user = await db.create_or_update_user(
            telegram_id=12345,
            username="test_user",
            first_name="Test"
        )

        self.assertIsNotNone(user)
        self.assertEqual(user.telegram_id, 12345)
        self.assertEqual(user.username, "test_user")

        # Проверяем получение пользователя
        retrieved_user = await db.get_user(12345)
        self.assertIsNotNone(retrieved_user)
        self.assertEqual(retrieved_user.telegram_id, 12345)

    async def test_add_message(self):
        """Тест добавления сообщения"""
        await db.create_or_update_user(telegram_id=12345)

        await db.add_message(12345, "user", "Привет!")
        await db.add_message(12345, "assistant", "Привет! Как дела?")

        messages = await db.get_user_messages(12345, limit=10)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[0].content, "Привет!")
        self.assertEqual(messages[1].role, "assistant")

    async def test_update_stats(self):
        """Тест обновления статистики"""
        await db.create_or_update_user(telegram_id=12345)

        await db.update_stats(12345, requests_count=1, tokens_used=100)
        await db.update_stats(12345, command='start')

        stats = await db.get_stats(12345)
        self.assertIsNotNone(stats)
        self.assertEqual(stats.requests_count, 1)
        self.assertEqual(stats.tokens_used, 100)
        self.assertEqual(stats.commands_used.get('start'), 1)

    async def test_gemini_service_list_models(self):
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
                self.assertGreater(len(models), 0)

    async def test_rate_limit_middleware(self):
        """Тест rate limiting middleware"""
        from middlewares.rate_limit import RateLimitMiddleware

        middleware = RateLimitMiddleware(max_requests=2, time_window=60)

        # Первые два запроса должны пройти
        self.assertTrue(await middleware.check_rate_limit(12345))
        self.assertTrue(await middleware.check_rate_limit(12345))

        # Третий запрос должен быть заблокирован
        self.assertFalse(await middleware.check_rate_limit(12345))


if __name__ == '__main__':
    unittest.main()
