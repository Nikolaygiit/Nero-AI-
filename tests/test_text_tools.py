"""
Тесты для модуля utils.text_tools
"""

import sys
import unittest
from unittest.mock import MagicMock, patch


class TestTextTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Импортируем модуль с замоканными зависимостями, чтобы избежать
        Global State Pollution и ошибок импорта из-за отсутствия пакетов.
        """
        # Создаем моки для отсутствующих зависимостей
        mock_modules = {
            "telegram": MagicMock(),
            "telegram.ext": MagicMock(),
            "telegram.error": MagicMock(),
            "sqlalchemy": MagicMock(),
            "sqlalchemy.ext.asyncio": MagicMock(),
            "httpx": MagicMock(),
            "pydantic": MagicMock(),
            "pydantic_settings": MagicMock(),
        }

        # Используем patch.dict для временной подмены sys.modules
        with patch.dict(sys.modules, mock_modules):
            # Если модуль уже был загружен (например, с ошибками), удаляем его из кэша
            if "utils.text_tools" in sys.modules:
                del sys.modules["utils.text_tools"]

            # Мы не можем безопасно удалить 'utils', так как это может сломать другие импорты,
            # но так как мы запускаем тесты изолированно или patch.dict восстанавливает состояние,
            # это должно быть безопасно.

            import utils.text_tools

            cls.text_tools = utils.text_tools

    def test_sanitize_markdown_balanced(self):
        """Тест: корректная разметка не изменяется"""
        sanitize_markdown = self.text_tools.sanitize_markdown
        self.assertEqual(sanitize_markdown("Hello *world*"), "Hello *world*")
        self.assertEqual(sanitize_markdown("Hello _world_"), "Hello _world_")
        self.assertEqual(sanitize_markdown("Hello ```code```"), "Hello ```code```")

    def test_sanitize_markdown_odd_stars(self):
        """Тест: незакрытые звёздочки (удаляется первая)"""
        sanitize_markdown = self.text_tools.sanitize_markdown
        self.assertEqual(sanitize_markdown("Hello *world"), "Hello world")
        self.assertEqual(sanitize_markdown("*Hello world"), "Hello world")
        self.assertEqual(sanitize_markdown("*Hello* world*"), "Hello* world*")

    def test_sanitize_markdown_odd_underscores(self):
        """Тест: незакрытые подчеркивания (экранируется первое)"""
        sanitize_markdown = self.text_tools.sanitize_markdown
        self.assertEqual(sanitize_markdown("Hello _world"), "Hello \\_world")
        self.assertEqual(sanitize_markdown("_Hello world"), "\\_Hello world")
        self.assertEqual(sanitize_markdown("_Hello_ world_"), "\\_Hello_ world_")

    def test_sanitize_markdown_odd_code_blocks(self):
        """Тест: незакрытые блоки кода (добавляется закрывающий)"""
        sanitize_markdown = self.text_tools.sanitize_markdown
        expected = "Hello ```code\n```"
        self.assertEqual(sanitize_markdown("Hello ```code"), expected)

    def test_sanitize_markdown_empty_and_none(self):
        """Тест: пустая строка и None"""
        sanitize_markdown = self.text_tools.sanitize_markdown
        self.assertEqual(sanitize_markdown(""), "")
        self.assertEqual(sanitize_markdown(None), "")

    def test_sanitize_markdown_non_string(self):
        """Тест: нестроковый ввод"""
        sanitize_markdown = self.text_tools.sanitize_markdown
        self.assertEqual(sanitize_markdown(123), 123)
        self.assertEqual(sanitize_markdown(0), "")

    def test_truncate_for_telegram(self):
        """Тест обрезки текста"""
        truncate_for_telegram = self.text_tools.truncate_for_telegram
        short_text = "Short text"
        self.assertEqual(truncate_for_telegram(short_text), short_text)

        long_text = "a" * 4096
        self.assertEqual(truncate_for_telegram(long_text), long_text)

        very_long_text = "a" * 4097
        expected = "a" * 4093 + "..."
        self.assertEqual(truncate_for_telegram(very_long_text), expected)


if __name__ == "__main__":
    unittest.main()
