"""
Общие константы и типы для LLM (Gemini/cascade). Используются в services.gemini и services.llm_cascade.
Ограничение одновременных запросов к API (semaphore) для нагрузки ~80k пользователей.
"""

import asyncio
from typing import Any, Dict, List, TypedDict, Union

import config

# Путь к chat completions (OpenAI-совместимый API)
CHAT_URL_PATH = "/chat/completions"

# Таймауты (секунды)
DEFAULT_REQUEST_TIMEOUT = 60.0
MODEL_TIMEOUT_SEC = getattr(config, "MODEL_TIMEOUT_SEC", 10) or 10

# Лимит одновременных запросов к LLM — защита от перегрузки API и очереди при высокой нагрузке
_raw = getattr(config.settings, "MAX_CONCURRENT_LLM_REQUESTS", 50)
MAX_CONCURRENT_LLM = int(_raw) if isinstance(_raw, int) else 50
llm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM)


def build_chat_url(api_base: str) -> str:
    """Полный URL для /chat/completions."""
    return f"{api_base.rstrip('/')}{CHAT_URL_PATH}"


def build_headers(api_key: str) -> Dict[str, str]:
    """Заголовки для запросов к LLM API."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


# --- Типизация формата сообщений API (OpenAI-совместимый) ---


class TextMessagePart(TypedDict, total=False):
    type: str  # "text"
    text: str


class ImageUrlPart(TypedDict, total=False):
    type: str  # "image_url"
    image_url: Dict[str, str]


# Один элемент content: строка или multimodal (text + image_url)
MessageContent = Union[str, List[Dict[str, Any]]]


class ChatMessage(TypedDict, total=False):
    """Одно сообщение в списке messages для chat/completions."""

    role: str  # "system" | "user" | "assistant"
    content: MessageContent
