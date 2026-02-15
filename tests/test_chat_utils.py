# ruff: noqa: E402
import sys
from unittest.mock import MagicMock


# Mock classes for telegram (since utils.chat_utils imports it)
class MockInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class MockInlineKeyboardButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


# Mock sys.modules for telegram
sys.modules["telegram"] = MagicMock()
sys.modules["telegram"].InlineKeyboardMarkup = MockInlineKeyboardMarkup
sys.modules["telegram"].InlineKeyboardButton = MockInlineKeyboardButton

# IMPORTANT: Mock submodules like telegram.ext, telegram.error because utils/__init__.py might import them
sys.modules["telegram.ext"] = MagicMock()
sys.modules["telegram.error"] = MagicMock()
sys.modules["telegram.constants"] = MagicMock()

# Mock other dependencies that utils package might accidentally pull in
sys.modules["structlog"] = MagicMock()

# We don't need to mock handlers or services anymore, as utils/chat_utils is standalone
# But if utils/__init__.py imports error_middleware which imports config or database...
sys.modules["config"] = MagicMock()
sys.modules["database"] = MagicMock()


# Import from the new location
from utils.chat_utils import make_regenerate_keyboard, split_long_message


def test_split_long_message_short():
    text = "Short message"
    parts = split_long_message(text)
    assert len(parts) == 1
    assert parts[0] == text


def test_split_long_message_exact_limit():
    text = "a" * 4096
    parts = split_long_message(text, max_length=4096)
    assert len(parts) == 1
    assert parts[0] == text


def test_split_long_message_just_over_limit():
    text = "a" * 4097
    parts = split_long_message(text, max_length=4096)
    assert len(parts) == 2
    assert parts[0] == "a" * 4096
    assert parts[1] == "a"


def test_split_long_message_with_code_block_fitting():
    code = "```\ncode\n```"
    text = "text " + code
    parts = split_long_message(text, max_length=100)
    assert len(parts) == 1
    assert parts[0] == text


def test_split_long_message_with_code_block_too_large():
    # Code block itself is larger than max_length
    code = "```" + "a" * 100 + "```"  # 106 chars
    text = "prefix " + code
    # max_length=50
    parts = split_long_message(text, max_length=50)

    assert len(parts) >= 3
    assert parts[0] == "prefix "
    assert parts[1].startswith("```")


def test_make_regenerate_keyboard():
    kb = make_regenerate_keyboard(123, "req_id")
    assert isinstance(kb, MockInlineKeyboardMarkup)
    assert len(kb.inline_keyboard) == 2
    assert kb.inline_keyboard[0][0].callback_data == "fav_123"
    assert kb.inline_keyboard[0][1].callback_data == "retry_123_req_id"
    assert kb.inline_keyboard[1][0].callback_data == "rephrase_123"
