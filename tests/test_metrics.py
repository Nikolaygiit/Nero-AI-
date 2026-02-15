# ruff: noqa: E402, I001
import sys
from unittest.mock import MagicMock
import pytest

# MOCK DEPENDENCIES BEFORE IMPORT
# utils/__init__.py imports error_middleware -> config -> pydantic
# We need to mock these to test metrics.py in isolation
mock_modules = [
    'telegram', 'telegram.ext', 'telegram.error',
    'sqlalchemy', 'sqlalchemy.orm', 'sqlalchemy.ext.asyncio',
    'httpx',
    'pydantic', 'pydantic_settings', 'dotenv',
    # We can mock prometheus_client to ensure consistent behavior regardless of installation
    'prometheus_client'
]
for mod in mock_modules:
    sys.modules[mod] = MagicMock()

# Now we can safely import
# Note: Since utils/__init__.py runs, it will import error_middleware, which imports config.
# Config instantiation might fail if pydantic is mocked too aggressively (e.g. Field arguments).
# But since we just want imports to pass, MagicMock usually works.
from utils.metrics import _parse_model_key

class TestMetrics:
    def test_parse_model_key_normal(self):
        """Тест обычного формата provider:model"""
        assert _parse_model_key("artemox:gemini-2.0-flash") == ("artemox", "gemini-2.0-flash")

    def test_parse_model_key_no_provider(self):
        """Тест модели без провайдера (нет двоеточия)"""
        assert _parse_model_key("gemini-1.5") == ("unknown", "gemini-1.5")

    def test_parse_model_key_multiple_colons(self):
        """Тест того, что разделение идет только по первому двоеточию"""
        assert _parse_model_key("provider:model:version:1") == ("provider", "model:version:1")

    def test_parse_model_key_empty(self):
        """Тест пустой строки"""
        assert _parse_model_key("") == ("unknown", "unknown")

    def test_parse_model_key_none(self):
        """Тест передачи None (должен возвращать unknown, unknown)"""
        # Текущая реализация упадет здесь с TypeError
        # Мы проверим это, чтобы подтвердить необходимость фикса
        try:
            result = _parse_model_key(None)
            assert result == ("unknown", "unknown")
        except TypeError:
            pytest.fail("Function raised TypeError on None input")
        except AttributeError:
             pytest.fail("Function raised AttributeError on None input")
