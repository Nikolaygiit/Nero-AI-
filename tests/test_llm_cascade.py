"""
Тесты для services.llm_cascade: CircuitBreaker и chat_completion (с моками).
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Моки до импорта
sys.modules["config"] = MagicMock()
mock_config = sys.modules["config"]
mock_config.GEMINI_API_KEY = "key"
mock_config.GEMINI_API_BASE = "https://api.test/v1"
mock_config.PREFERRED_MODELS = ["model-a", "model-b"]
mock_config.settings = MagicMock()
mock_config.settings.DEEPSEEK_API_KEY = ""
mock_config.settings.OPENAI_API_KEY = ""
mock_config.MODEL_TIMEOUT_SEC = 10
mock_config.CIRCUIT_FAILURE_THRESHOLD = 3
mock_config.CIRCUIT_COOLDOWN_SEC = 60

if "services.llm_cascade" in sys.modules:
    del sys.modules["services.llm_cascade"]
from services.llm_cascade import (  # noqa: E402, I001
    CircuitBreaker,
    CircuitState,
    LLMProvider,
    _chat_completion_request,
    _get_providers,
    chat_completion,
)


# --- CircuitBreaker ---


class TestCircuitBreaker:
    def test_init(self):
        cb = CircuitBreaker(threshold=2, cooldown=5)
        assert cb.threshold == 2
        assert cb.cooldown == 5

    def test_is_open_empty_false(self):
        cb = CircuitBreaker(threshold=2, cooldown=5)
        assert cb.is_open("artemox:model-a") is False

    def test_record_failure_under_threshold(self):
        cb = CircuitBreaker(threshold=3, cooldown=5)
        cb.record_failure("p:m")
        cb.record_failure("p:m")
        assert cb.is_open("p:m") is False

    def test_record_failure_opens_circuit(self):
        cb = CircuitBreaker(threshold=2, cooldown=5)
        cb.record_failure("p:m")
        cb.record_failure("p:m")
        assert cb.is_open("p:m") is True

    def test_record_success_resets_failures(self):
        cb = CircuitBreaker(threshold=2, cooldown=5)
        cb.record_failure("p:m")
        cb.record_failure("p:m")
        cb.record_success("p:m")
        # После success счётчик обнуляется; is_open может ещё быть True из-за open_until
        assert "p:m" in cb._states
        assert cb._states["p:m"].failures == 0


class TestCircuitState:
    def test_defaults(self):
        s = CircuitState()
        assert s.failures == 0
        assert s.last_failure_at == 0
        assert s.open_until == 0


# --- _get_providers ---


def test_get_providers_returns_artemox():
    providers = _get_providers()
    assert len(providers) >= 1
    artemox = providers[0]
    assert artemox.name == "artemox"
    assert artemox.api_base == "https://api.test/v1"
    assert artemox.api_key == "key"
    assert "model-a" in artemox.models


# --- _chat_completion_request (мок httpx) ---


@pytest.mark.asyncio
async def test_chat_completion_request_success():
    provider = LLMProvider(
        name="test",
        api_base="https://api.test/v1",
        api_key="key",
        models=["m1"],
        timeout=10.0,
    )
    messages = [{"role": "user", "content": "Hi"}]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b""
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "Hello"}}],
        "usage": {"total_tokens": 5},
    }
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("services.llm_cascade.httpx.AsyncClient", return_value=mock_client),
        patch("services.llm_cascade.circuit_breaker") as mock_cb,
    ):
        text, tokens, err = await _chat_completion_request(provider, "m1", messages, max_tokens=100)
    assert err is None
    assert text == "Hello"
    assert tokens == 5
    mock_cb.record_success.assert_called_once_with("test:m1")


@pytest.mark.asyncio
async def test_chat_completion_request_http_error():
    provider = LLMProvider(
        name="test",
        api_base="https://api.test/v1",
        api_key="key",
        models=["m1"],
        timeout=10.0,
    )
    messages = [{"role": "user", "content": "Hi"}]
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.content = b""
    mock_resp.text = "Server Error"
    mock_resp.json.return_value = {}
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.llm_cascade.httpx.AsyncClient", return_value=mock_client):
        text, tokens, err = await _chat_completion_request(provider, "m1", messages, max_tokens=100)
    assert text is None
    assert tokens is None
    assert err is not None
    assert "500" in str(err)


# --- chat_completion (мок _get_providers и _chat_completion_request) ---


@pytest.mark.asyncio
async def test_chat_completion_returns_on_first_success():
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hi"},
    ]
    fake_provider = LLMProvider(
        name="artemox",
        api_base="https://api.test/v1",
        api_key="key",
        models=["m1"],
        timeout=10.0,
    )

    with (
        patch("services.llm_cascade._get_providers", return_value=[fake_provider]),
        patch(
            "services.llm_cascade._chat_completion_request",
            AsyncMock(return_value=("Reply", 10, None)),
        ),
        patch("services.llm_cascade.MODEL_TIMEOUT_SEC", 10),
    ):
        text, model_used, tokens = await chat_completion(messages, max_tokens=100)

    assert text == "Reply"
    assert model_used == "artemox:m1"
    assert tokens == 10


@pytest.mark.asyncio
async def test_chat_completion_raises_when_all_fail():
    messages = [{"role": "user", "content": "Hi"}]
    fake_provider = LLMProvider(
        name="artemox",
        api_base="https://api.test/v1",
        api_key="key",
        models=["m1"],
        timeout=10.0,
    )

    with (
        patch("services.llm_cascade._get_providers", return_value=[fake_provider]),
        patch(
            "services.llm_cascade._chat_completion_request",
            AsyncMock(return_value=(None, None, Exception("API error"))),
        ),
        patch("services.llm_cascade.MODEL_TIMEOUT_SEC", 10),
    ):
        with pytest.raises(Exception) as exc_info:
            await chat_completion(messages, max_tokens=100)
    assert "API error" in str(exc_info.value) or "failed" in str(exc_info.value).lower()
