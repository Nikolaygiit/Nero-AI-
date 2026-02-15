import sys
import os
from unittest.mock import MagicMock

# Mock all heavy dependencies
sys.modules['telegram'] = MagicMock()
sys.modules['telegram.error'] = MagicMock()
sys.modules['telegram.ext'] = MagicMock()
sys.modules['telegram.constants'] = MagicMock()

sys.modules['sqlalchemy'] = MagicMock()
sys.modules['database'] = MagicMock()
sys.modules['database.db'] = MagicMock()
sys.modules['database.models'] = MagicMock()

sys.modules['structlog'] = MagicMock()
sys.modules['httpx'] = MagicMock()  # Mock httpx
sys.modules['pydantic'] = MagicMock()
sys.modules['pydantic_settings'] = MagicMock()
sys.modules['config'] = MagicMock()

sys.modules['services'] = MagicMock()
sys.modules['services.gemini'] = MagicMock()
sys.modules['services.image_gen'] = MagicMock()
sys.modules['services.memory'] = MagicMock()
sys.modules['services.rag'] = MagicMock()

# Mock internal sibling modules to prevent them from being imported by handlers/__init__.py
sys.modules['handlers.basic'] = MagicMock()
sys.modules['handlers.admin'] = MagicMock()
sys.modules['handlers.callbacks'] = MagicMock()
sys.modules['handlers.commands'] = MagicMock()
sys.modules['handlers.conversation'] = MagicMock()
sys.modules['handlers.documents'] = MagicMock()
sys.modules['handlers.media'] = MagicMock()
sys.modules['handlers.payments'] = MagicMock()

# Mock middlewares
sys.modules['middlewares'] = MagicMock()
sys.modules['middlewares.rate_limit'] = MagicMock()
sys.modules['middlewares.usage_limit'] = MagicMock()

# Mock classes for telegram
class MockInlineKeyboardMarkup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard
class MockInlineKeyboardButton:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data

sys.modules['telegram'].InlineKeyboardMarkup = MockInlineKeyboardMarkup
sys.modules['telegram'].InlineKeyboardButton = MockInlineKeyboardButton

# Add current dir to path
sys.path.append(os.getcwd())

import pytest
# Try to import chat_utils.
from handlers.chat_utils import split_long_message, make_regenerate_keyboard

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
    code = "```" + "a" * 100 + "```" # 106 chars
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
