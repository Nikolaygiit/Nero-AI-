import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def truncate_for_telegram():
    """
    Fixture to import truncate_for_telegram with mocked dependencies.
    Ensures that 'utils' and its submodules are unloaded before import
    so they pick up the mocks, and restores the environment afterwards.
    """
    # Mocks for dependencies used in utils/__init__.py -> error_middleware.py
    mock_modules = {
        'telegram': MagicMock(),
        'telegram.ext': MagicMock(),
        'telegram.error': MagicMock(),
        'sqlalchemy': MagicMock(),
        'httpx': MagicMock(),
        'pydantic': MagicMock(),
        'pydantic_settings': MagicMock(),
        'config': MagicMock(),
    }

    # Use patch.dict to safely modify sys.modules and restore it automatically
    with patch.dict(sys.modules, mock_modules):
        # We must unload 'utils' and 'utils.text_tools' to force re-import
        # inside this patched environment.
        # We iterate over a copy of keys to avoid runtime error during deletion.
        for mod_name in list(sys.modules):
            if mod_name.startswith("utils"):
                del sys.modules[mod_name]

        # Now import the function. It will trigger utils/__init__.py
        # which will import error_middleware, which imports mocks.
        from utils.text_tools import truncate_for_telegram
        yield truncate_for_telegram

def test_short_text(truncate_for_telegram):
    """Text shorter than max_length should be returned as is."""
    text = "Short text"
    assert truncate_for_telegram(text) == text

def test_exact_length_text(truncate_for_telegram):
    """Text exactly max_length should be returned as is."""
    text = "a" * 4096
    assert truncate_for_telegram(text) == text

def test_long_text(truncate_for_telegram):
    """Text longer than max_length should be truncated with ellipsis."""
    # max_length defaults to 4096
    text = "a" * 5000
    expected = "a" * (4096 - 3) + "..."
    assert truncate_for_telegram(text) == expected
    assert len(expected) == 4096

def test_custom_max_length(truncate_for_telegram):
    """Function should respect custom max_length."""
    text = "abcdefghij"
    max_len = 5
    expected = "ab..."
    assert truncate_for_telegram(text, max_length=max_len) == expected
    assert len(expected) == max_len

def test_empty_text(truncate_for_telegram):
    """Empty text should return empty string."""
    assert truncate_for_telegram("") == ""

def test_very_long_text_custom_length(truncate_for_telegram):
    """Verify truncation with custom length on very long text."""
    text = "a" * 100
    max_len = 10
    expected = "aaaaaaa..."
    assert truncate_for_telegram(text, max_length=max_len) == expected
    assert len(expected) == max_len

def test_boundary_conditions(truncate_for_telegram):
    """Test boundary conditions for truncation."""
    # max_length = 3
    # "abcd"[:3-3] + "..." -> "" + "..." -> "..."
    assert truncate_for_telegram("abcd", max_length=3) == "..."

    # max_length = 4
    # "abcde"[:4-3] + "..." -> "a" + "..." -> "a..."
    assert truncate_for_telegram("abcde", max_length=4) == "a..."
