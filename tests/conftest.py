"""
Pytest conftest: общие фикстуры и настройка путей.
"""

import os
import sys

import pytest

# Корень проекта в path для всех тестов
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def mock_update():
    """Update с message.reply_text, effective_user.id и т.д."""
    from tests.mocks import make_mock_update

    return make_mock_update()


@pytest.fixture
def mock_context():
    """Context с user_data."""
    from tests.mocks import make_mock_context

    return make_mock_context()


@pytest.fixture
def mock_db():
    """Мок database.db с AsyncMock-методами."""
    from tests.mocks import make_mock_db

    return make_mock_db()
