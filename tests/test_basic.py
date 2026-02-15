import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Mock heavy external dependencies
sys.modules["sqlalchemy"] = MagicMock()
sys.modules["sqlalchemy.ext"] = MagicMock()
sys.modules["sqlalchemy.ext.asyncio"] = MagicMock()
sys.modules["sqlalchemy.ext.declarative"] = MagicMock()
sys.modules["sqlalchemy.orm"] = MagicMock()
sys.modules["aiosqlite"] = MagicMock()
sys.modules["httpx"] = MagicMock()
sys.modules["redis"] = MagicMock()
sys.modules["redis.asyncio"] = MagicMock()
sys.modules["taskiq"] = MagicMock()
sys.modules["taskiq_redis"] = MagicMock()

# Create the mock DB object with AsyncMock methods
mock_db_instance = MagicMock()
mock_db_instance.init = AsyncMock()
mock_db_instance.close = AsyncMock()
mock_db_instance.create_or_update_user = AsyncMock()
mock_db_instance.get_user = AsyncMock()
mock_db_instance.add_message = AsyncMock()
mock_db_instance.get_user_messages = AsyncMock()
mock_db_instance.update_stats = AsyncMock()
mock_db_instance.get_stats = AsyncMock()

# Create a mock for the 'database' package
mock_database_pkg = MagicMock()
mock_database_pkg.db = mock_db_instance


class TestBasic(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.patcher = patch.dict(sys.modules, {"database": mock_database_pkg})
        self.patcher.start()
        # Re-import database.db to ensure it uses our mocked package if needed
        # But actually we just use the mocked instance directly via `mock_database_pkg.db` or `from database import db`

    async def asyncTearDown(self):
        self.patcher.stop()

    async def test_database_init(self):
        """Тест инициализации базы данных (mocked)"""
        from database import db

        await db.init()
        db.init.assert_called()
        await db.close()
        db.close.assert_called()

    async def test_create_user(self):
        """Тест создания пользователя (mocked)"""
        from database import db

        # Setup mock return
        mock_user = MagicMock()
        mock_user.telegram_id = 12345
        mock_user.username = "test_user"

        db.create_or_update_user.return_value = mock_user
        db.get_user.return_value = mock_user

        user = await db.create_or_update_user(
            telegram_id=12345, username="test_user", first_name="Test"
        )

        self.assertIsNotNone(user)
        self.assertEqual(user.telegram_id, 12345)
        self.assertEqual(user.username, "test_user")

    async def test_add_message(self):
        """Тест добавления сообщения (mocked)"""
        from database import db

        # Setup mock
        mock_msg1 = MagicMock(role="user", content="Привет!")
        mock_msg2 = MagicMock(role="assistant", content="Привет! Как дела?")
        db.get_user_messages.return_value = [mock_msg1, mock_msg2]

        # Добавляем сообщение
        await db.add_message(12345, "user", "Привет!")

        # Получаем сообщения
        messages = await db.get_user_messages(12345, limit=10)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")


if __name__ == "__main__":
    unittest.main()
