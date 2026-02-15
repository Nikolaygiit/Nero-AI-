import sys
import unittest.mock
import pytest

# Mock dependencies before import to prevent ImportErrors and execution of config.py
# utils/__init__.py imports error_middleware which imports telegram, httpx, config etc.
sys.modules['telegram'] = unittest.mock.MagicMock()
sys.modules['telegram.ext'] = unittest.mock.MagicMock()
sys.modules['telegram.error'] = unittest.mock.MagicMock()
sys.modules['sqlalchemy'] = unittest.mock.MagicMock()
sys.modules['httpx'] = unittest.mock.MagicMock()
sys.modules['pydantic'] = unittest.mock.MagicMock()
sys.modules['pydantic_settings'] = unittest.mock.MagicMock()
sys.modules['config'] = unittest.mock.MagicMock()

# Now import the target function
from utils.text_tools import truncate_for_telegram

def test_short_text():
    """Text shorter than max_length should be returned as is."""
    text = "Short text"
    assert truncate_for_telegram(text) == text

def test_exact_length_text():
    """Text exactly max_length should be returned as is."""
    text = "a" * 4096
    assert truncate_for_telegram(text) == text

def test_long_text():
    """Text longer than max_length should be truncated with ellipsis."""
    # max_length defaults to 4096
    text = "a" * 5000
    expected = "a" * (4096 - 3) + "..."
    assert truncate_for_telegram(text) == expected
    assert len(expected) == 4096

def test_custom_max_length():
    """Function should respect custom max_length."""
    text = "abcdefghij"
    max_len = 5
    expected = "ab..."
    assert truncate_for_telegram(text, max_length=max_len) == expected
    assert len(expected) == max_len

def test_empty_text():
    """Empty text should return empty string."""
    assert truncate_for_telegram("") == ""

def test_very_long_text_custom_length():
    """Verify truncation with custom length on very long text."""
    text = "a" * 100
    max_len = 10
    expected = "aaaaaaa..."
    assert truncate_for_telegram(text, max_length=max_len) == expected
    assert len(expected) == max_len

def test_boundary_conditions():
    """Test boundary conditions for truncation."""
    # max_length = 3
    # "abcd"[:3-3] + "..." -> "" + "..." -> "..."
    assert truncate_for_telegram("abcd", max_length=3) == "..."

    # max_length = 4
    # "abcde"[:4-3] + "..." -> "a" + "..." -> "a..."
    assert truncate_for_telegram("abcde", max_length=4) == "a..."
