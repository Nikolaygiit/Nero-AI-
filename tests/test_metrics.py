import sys
from unittest.mock import MagicMock, patch

import pytest


# Используем фикстуру для изоляции моков
@pytest.fixture(scope="function")
def metrics_module():
    """
    Импортирует модуль metrics с замоканными зависимостями.
    Гарантирует восстановление sys.modules после теста.
    """
    # Список модулей для мока (зависимости utils/__init__.py)
    mock_modules_dict = {
        'telegram': MagicMock(),
        'telegram.ext': MagicMock(),
        'telegram.error': MagicMock(),
        'sqlalchemy': MagicMock(),
        'sqlalchemy.orm': MagicMock(),
        'sqlalchemy.ext.asyncio': MagicMock(),
        'httpx': MagicMock(),
        'pydantic': MagicMock(),
        'pydantic_settings': MagicMock(),
        'dotenv': MagicMock(),
        'prometheus_client': MagicMock()
    }

    # Сохраняем состояние sys.modules
    with patch.dict(sys.modules, mock_modules_dict):
        # Удаляем utils и utils.metrics из sys.modules, чтобы вызвать повторный импорт
        # внутри контекста с моками
        if 'utils' in sys.modules:
            del sys.modules['utils']
        if 'utils.metrics' in sys.modules:
            del sys.modules['utils.metrics']

        import utils.metrics
        yield utils.metrics

    # После выхода из контекста patch.dict восстановит старые значения в sys.modules.
    # Но 'utils.metrics' (загруженный с моками) может остаться, если его не было раньше.
    # Чтобы не портить другие тесты, лучше удалить его, если он ссылается на моки.
    # Простейший способ - просто удалить 'utils' и подмодули из кэша, чтобы другие тесты
    # импортировали их заново с настоящими зависимостями (или падали, если зависимостей нет, как локально).
    keys_to_remove = [k for k in sys.modules if k.startswith('utils')]
    for k in keys_to_remove:
        del sys.modules[k]

class TestMetrics:
    def test_parse_model_key_normal(self, metrics_module):
        """Тест обычного формата provider:model"""
        assert metrics_module._parse_model_key("artemox:gemini-2.0-flash") == ("artemox", "gemini-2.0-flash")

    def test_parse_model_key_no_provider(self, metrics_module):
        """Тест модели без провайдера (нет двоеточия)"""
        assert metrics_module._parse_model_key("gemini-1.5") == ("unknown", "gemini-1.5")

    def test_parse_model_key_multiple_colons(self, metrics_module):
        """Тест того, что разделение идет только по первому двоеточию"""
        assert metrics_module._parse_model_key("provider:model:version:1") == ("provider", "model:version:1")

    def test_parse_model_key_empty(self, metrics_module):
        """Тест пустой строки"""
        assert metrics_module._parse_model_key("") == ("unknown", "unknown")

    def test_parse_model_key_none(self, metrics_module):
        """Тест передачи None (должен возвращать unknown, unknown)"""
        assert metrics_module._parse_model_key(None) == ("unknown", "unknown")
