
import importlib
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Add the project root to sys.path to allow importing handlers
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestCalculatorCommand(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Patch sys.modules to mock dependencies
        self.modules_patcher = patch.dict(sys.modules, {
            'telegram': MagicMock(),
            'telegram.ext': MagicMock(),
            'telegram.error': MagicMock(),
            'telegram.constants': MagicMock(),
            'database': MagicMock(),
            'services.gemini': MagicMock(),
            'services.image_gen': MagicMock(),
            'middlewares.rate_limit': MagicMock(),
            'utils.i18n': MagicMock(),
            'config': MagicMock(),
            'tasks.image_tasks': MagicMock(),
            'tasks.broker': MagicMock(),
        })
        self.modules_patcher.start()

        # Import the module under test directly to avoid importing the entire handlers package
        file_path = os.path.join(os.path.dirname(__file__), '..', 'handlers', 'commands.py')
        spec = importlib.util.spec_from_file_location("handlers.commands_test", file_path)
        self.commands_module = importlib.util.module_from_spec(spec)
        # Add to sys.modules so imports inside it work (if any relative imports exist)
        sys.modules["handlers.commands_test"] = self.commands_module
        spec.loader.exec_module(self.commands_module)

    async def asyncTearDown(self):
        self.modules_patcher.stop()

    async def test_no_args(self):
        """Test calculator command with no arguments"""
        update = AsyncMock()
        context = MagicMock()
        context.args = []

        await self.commands_module.calculator_command(update, context)

        # Verify help message is sent
        update.message.reply_text.assert_called_once()
        args, _ = update.message.reply_text.call_args
        self.assertIn("Калькулятор", args[0])
        self.assertIn("Укажите выражение", args[0])

    async def test_empty_expression(self):
        """Test calculator command with empty expression"""
        update = AsyncMock()
        context = MagicMock()
        context.args = ["   "]

        await self.commands_module.calculator_command(update, context)

        # Verify empty expression error
        update.message.reply_text.assert_called_once()
        args, _ = update.message.reply_text.call_args
        self.assertIn("Укажите выражение", args[0])

    async def test_invalid_chars(self):
        """Test calculator command with invalid characters"""
        update = AsyncMock()
        context = MagicMock()
        context.args = ["2", "+", "abc"]

        await self.commands_module.calculator_command(update, context)

        # Verify invalid chars error
        update.message.reply_text.assert_called_once()
        args, _ = update.message.reply_text.call_args
        self.assertIn("недопустимые символы", args[0])

    async def test_too_long_expression(self):
        """Test calculator command with too long expression"""
        update = AsyncMock()
        context = MagicMock()
        # Create a valid but too long expression
        long_expr = "1" * 201
        context.args = [long_expr]

        await self.commands_module.calculator_command(update, context)

        # Verify too long error
        update.message.reply_text.assert_called_once()
        args, _ = update.message.reply_text.call_args
        self.assertIn("слишком длинное", args[0])

    async def test_rate_limit_exceeded(self):
        """Test calculator command when rate limit is exceeded"""
        update = AsyncMock()
        context = MagicMock()
        context.args = ["2", "+", "2"]

        # Mock rate limit middleware
        mock_rate_limit = self.commands_module.rate_limit_middleware
        mock_rate_limit.check_rate_limit = AsyncMock(return_value=False)
        mock_rate_limit.time_window = 60

        await self.commands_module.calculator_command(update, context)

        # Verify rate limit error
        mock_rate_limit.check_rate_limit.assert_called_once()
        update.message.reply_text.assert_called_once()
        args, _ = update.message.reply_text.call_args
        self.assertIn("Слишком много запросов", args[0])

    async def test_valid_expression(self):
        """Test calculator command with valid expression (Happy Path)"""
        update = AsyncMock()
        context = MagicMock()
        context.args = ["2", "+", "2"]
        update.effective_user.id = 12345

        # Mock dependencies
        mock_rate_limit = self.commands_module.rate_limit_middleware
        mock_rate_limit.check_rate_limit = AsyncMock(return_value=True)

        mock_gemini = self.commands_module.gemini_service
        mock_gemini.generate_content = AsyncMock(return_value="4")

        mock_db = self.commands_module.db
        mock_db.update_stats = AsyncMock()

        await self.commands_module.calculator_command(update, context)

        # Verify interactions
        mock_rate_limit.check_rate_limit.assert_called_once_with(12345)
        update.message.reply_chat_action.assert_called_once_with("typing")

        # Check prompt
        mock_gemini.generate_content.assert_called_once()
        args, _ = mock_gemini.generate_content.call_args
        self.assertIn("2 + 2", args[0])
        self.assertIn("Вычисли", args[0])

        # Check reply
        update.message.reply_text.assert_called_once()
        args, _ = update.message.reply_text.call_args
        self.assertIn("4", args[0])
        self.assertIn("Результат", args[0])

        # Check stats update
        mock_db.update_stats.assert_called_once_with(12345, command='calculator')

    async def test_service_error(self):
        """Test calculator command when service fails"""
        update = AsyncMock()
        context = MagicMock()
        context.args = ["2", "+", "2"]
        update.effective_user.id = 12345

        # Mock dependencies
        mock_rate_limit = self.commands_module.rate_limit_middleware
        mock_rate_limit.check_rate_limit = AsyncMock(return_value=True)

        mock_gemini = self.commands_module.gemini_service
        mock_gemini.generate_content = AsyncMock(side_effect=Exception("API Error"))

        await self.commands_module.calculator_command(update, context)

        # Verify error handling
        update.message.reply_text.assert_called_once()
        args, _ = update.message.reply_text.call_args
        self.assertIn("Ошибка вычисления", args[0])
        self.assertIn("API Error", args[0])

if __name__ == '__main__':
    unittest.main()
