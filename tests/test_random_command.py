import unittest
from unittest.mock import MagicMock, AsyncMock, patch, ANY
import sys
import importlib

class TestRandomCommand(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Create mocks for dependencies
        cls.mock_telegram = MagicMock()
        cls.mock_telegram.Update = MagicMock()
        cls.mock_telegram.ext = MagicMock()
        cls.mock_telegram.ext.ContextTypes = MagicMock()

        # Mock telegram.error.NetworkError
        cls.mock_telegram_error = MagicMock()
        # It must be a class inheriting from Exception
        class NetworkError(Exception): pass
        cls.mock_telegram_error.NetworkError = NetworkError

        cls.mock_database = MagicMock()
        cls.mock_database.db = MagicMock()
        cls.mock_database.db.update_stats = AsyncMock()

        cls.mock_gemini = MagicMock()
        cls.mock_gemini.gemini_service = MagicMock()

        cls.mock_image_gen = MagicMock()
        cls.mock_image_gen.image_generator = MagicMock()

        cls.mock_rag = MagicMock()

        cls.mock_rate_limit = MagicMock()
        cls.mock_rate_limit.rate_limit_middleware = MagicMock()

        cls.mock_i18n = MagicMock()
        cls.mock_i18n.t = MagicMock(return_value="translated_text")

        cls.mock_config = MagicMock()
        cls.mock_config.PERSONAS = {}

        cls.mock_tasks = MagicMock()

        cls.mock_httpx = MagicMock()
        cls.mock_sqlalchemy = MagicMock()
        cls.mock_pydantic = MagicMock()
        cls.mock_structlog = MagicMock()

        # Modules to patch
        cls.modules_patcher = patch.dict(sys.modules, {
            'telegram': cls.mock_telegram,
            'telegram.ext': cls.mock_telegram.ext,
            'httpx': cls.mock_httpx,
            'sqlalchemy': cls.mock_sqlalchemy,
            'pydantic': cls.mock_pydantic,
            'structlog': cls.mock_structlog,
            'telegram.error': cls.mock_telegram_error,
            'database': cls.mock_database,
            'services.gemini': cls.mock_gemini,
            'services.image_gen': cls.mock_image_gen,
            'services.rag': cls.mock_rag,
            'middlewares.rate_limit': cls.mock_rate_limit,
            'utils.i18n': cls.mock_i18n,
            'config': cls.mock_config,
            'tasks': cls.mock_tasks,
            'tasks.image_tasks': cls.mock_tasks,
            'tasks.broker': cls.mock_tasks,
        })
        cls.modules_patcher.start()

        # Ensure handlers.commands is imported with mocks
        if 'handlers.commands' in sys.modules:
            del sys.modules['handlers.commands']

        import handlers.commands
        cls.handlers_commands = handlers.commands

    @classmethod
    def tearDownClass(cls):
        cls.modules_patcher.stop()
        if 'handlers.commands' in sys.modules:
            del sys.modules['handlers.commands']

    async def asyncSetUp(self):
        # Reset mocks before each test
        self.mock_database.db.update_stats.reset_mock()
        self.update = MagicMock()
        self.context = MagicMock()
        self.update.effective_user.id = 12345
        self.update.message.reply_text = AsyncMock()

    async def test_random_no_args(self):
        """Test /random with no arguments (shows help)"""
        self.context.args = []
        await self.handlers_commands.random_command(self.update, self.context)

        self.update.message.reply_text.assert_called_once()
        args, _ = self.update.message.reply_text.call_args
        self.assertIn("Случайные значения", args[0])
        self.assertIn("/random number", args[0])

    async def test_random_number(self):
        """Test /random number [min] [max]"""
        self.context.args = ["number", "10", "20"]

        with patch('random.randint') as mock_randint:
            mock_randint.return_value = 15
            await self.handlers_commands.random_command(self.update, self.context)

            mock_randint.assert_called_with(10, 20)
            self.update.message.reply_text.assert_called_once()
            args, _ = self.update.message.reply_text.call_args
            self.assertIn("15", args[0])
            self.mock_database.db.update_stats.assert_called_with(12345, command='random')

    async def test_random_choice(self):
        """Test /random choice [item1] [item2]"""
        self.context.args = ["choice", "apple", "banana"]

        with patch('random.choice') as mock_choice:
            mock_choice.return_value = "apple"
            await self.handlers_commands.random_command(self.update, self.context)

            mock_choice.assert_called_with(["apple", "banana"])
            self.update.message.reply_text.assert_called_once()
            args, _ = self.update.message.reply_text.call_args
            self.assertIn("apple", args[0])
            self.mock_database.db.update_stats.assert_called_with(12345, command='random')

    async def test_random_coin(self):
        """Test /random coin"""
        self.context.args = ["coin"]

        with patch('random.choice') as mock_choice:
            mock_choice.return_value = "Орел"
            await self.handlers_commands.random_command(self.update, self.context)

            mock_choice.assert_called_with(["Орел", "Решка"])
            self.update.message.reply_text.assert_called_once()
            args, _ = self.update.message.reply_text.call_args
            self.assertIn("Орел", args[0])
            self.mock_database.db.update_stats.assert_called_with(12345, command='random')

    async def test_random_dice(self):
        """Test /random dice"""
        self.context.args = ["dice"]

        with patch('random.randint') as mock_randint:
            mock_randint.return_value = 4
            await self.handlers_commands.random_command(self.update, self.context)

            mock_randint.assert_called_with(1, 6)
            self.update.message.reply_text.assert_called_once()
            args, _ = self.update.message.reply_text.call_args
            self.assertIn("4", args[0])
            self.mock_database.db.update_stats.assert_called_with(12345, command='random')

    async def test_random_invalid_action(self):
        """Test /random with invalid action"""
        self.context.args = ["invalid"]
        await self.handlers_commands.random_command(self.update, self.context)

        self.update.message.reply_text.assert_called_once()
        args, _ = self.update.message.reply_text.call_args
        self.assertIn("Неверный формат команды", args[0])
        # Should not update stats on error/invalid command usage (based on implementation logic: if ... else: return)
        self.mock_database.db.update_stats.assert_not_called()

    async def test_random_number_missing_args(self):
        """Test /random number without enough args"""
        self.context.args = ["number", "10"] # Missing max
        # The code checks `len(context.args) >= 3` for number
        # If not met, it falls to `else` block (which says "Invalid format")?
        # Let's check the code:
        # if action == "number" and len(context.args) >= 3: ...
        # elif ...
        # else: ... reply "Invalid format"

        await self.handlers_commands.random_command(self.update, self.context)

        self.update.message.reply_text.assert_called_once()
        args, _ = self.update.message.reply_text.call_args
        self.assertIn("Неверный формат команды", args[0])

    async def test_random_exception(self):
        """Test exception handling in random_command"""
        self.context.args = ["number", "invalid", "invalid"] # int() will raise ValueError

        await self.handlers_commands.random_command(self.update, self.context)

        # Should catch exception and reply with error
        self.update.message.reply_text.assert_called_once()
        args, _ = self.update.message.reply_text.call_args
        self.assertIn("Ошибка:", args[0])

if __name__ == '__main__':
    unittest.main()
