"""
Circuit Breaker + Model Cascading — неубиваемость LLM API
Если основная модель падает или тормозит > N сек, автоматически переключаемся на резервную.
Поддержка fallback на DeepSeek/OpenAI при наличии ключей.
"""
import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

import config

logger = logging.getLogger(__name__)

# Таймаут одного запроса (сек)
MODEL_TIMEOUT_SEC = getattr(config, "MODEL_TIMEOUT_SEC", 10)

# Circuit Breaker: после N ошибок модель "открыта" на COOLDOWN_SEC
CIRCUIT_FAILURE_THRESHOLD = getattr(config, "CIRCUIT_FAILURE_THRESHOLD", 3)
CIRCUIT_COOLDOWN_SEC = getattr(config, "CIRCUIT_COOLDOWN_SEC", 60)


@dataclass
class CircuitState:
    """Состояние circuit breaker для одной модели"""
    failures: int = 0
    last_failure_at: float = 0
    open_until: float = 0


class CircuitBreaker:
    """Circuit Breaker: отключает модель после серии ошибок"""

    def __init__(self, threshold: int = CIRCUIT_FAILURE_THRESHOLD, cooldown: int = CIRCUIT_COOLDOWN_SEC):
        self.threshold = threshold
        self.cooldown = cooldown
        self._states: Dict[str, CircuitState] = {}

    def is_open(self, model_key: str) -> bool:
        now = time.monotonic()
        state = self._states.get(model_key)
        if not state:
            return False
        if state.open_until > now:
            return True
        if state.failures >= self.threshold and (now - state.last_failure_at) < self.cooldown:
            state.open_until = now + self.cooldown
            return True
        return False

    def record_success(self, model_key: str) -> None:
        if model_key in self._states:
            self._states[model_key].failures = 0

    def record_failure(self, model_key: str) -> None:
        now = time.monotonic()
        if model_key not in self._states:
            self._states[model_key] = CircuitState()
        s = self._states[model_key]
        s.failures += 1
        s.last_failure_at = now
        if s.failures >= self.threshold:
            s.open_until = now + self.cooldown
            logger.warning(f"Circuit OPEN for {model_key} (failures={s.failures}, cooldown={self.cooldown}s)")


circuit_breaker = CircuitBreaker()


@dataclass
class LLMProvider:
    """Провайдер LLM API (OpenAI-совместимый)"""
    name: str
    api_base: str
    api_key: str
    models: List[str]
    timeout: float = MODEL_TIMEOUT_SEC


def _get_providers() -> List[LLMProvider]:
    """Собирает список провайдеров из конфига: Artemox → DeepSeek → OpenAI"""
    providers: List[LLMProvider] = []

    # 1. Artemox (Gemini) — основной
    providers.append(LLMProvider(
        name="artemox",
        api_base=config.GEMINI_API_BASE,
        api_key=config.GEMINI_API_KEY,
        models=config.PREFERRED_MODELS[:8],
    ))

    # 2. DeepSeek — fallback
    deepseek_key = getattr(config.settings, "DEEPSEEK_API_KEY", "") or ""
    if deepseek_key and len(deepseek_key) > 5:
        providers.append(LLMProvider(
            name="deepseek",
            api_base="https://api.deepseek.com/v1",
            api_key=deepseek_key,
            models=["deepseek-chat", "deepseek-coder"],
        ))

    # 3. OpenAI — fallback
    openai_key = getattr(config.settings, "OPENAI_API_KEY", "") or ""
    if openai_key and len(openai_key) > 5:
        providers.append(LLMProvider(
            name="openai",
            api_base="https://api.openai.com/v1",
            api_key=openai_key,
            models=["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
        ))

    return providers


async def _chat_completion_request(
    provider: LLMProvider,
    model: str,
    messages: List[Dict[str, Any]],
    max_tokens: int = 4000,
    stream: bool = False,
) -> Tuple[Optional[str], Optional[int], Optional[Exception]]:
    """
    Один запрос к OpenAI-совместимому API.
    Returns: (text, total_tokens, error)
    """
    url = f"{provider.api_base.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {provider.api_key}",
        "Content-Type": "application/json",
    }
    data = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    model_key = f"{provider.name}:{model}"

    try:
        async with httpx.AsyncClient(timeout=provider.timeout) as client:
            if stream:
                full_text = ""
                async with client.stream("POST", url, headers=headers, json=data) as resp:
                    if resp.status_code != 200:
                        err_body = await resp.aread()
                        return None, None, Exception(f"HTTP {resp.status_code}: {err_body[:200]}")
                    async for line in resp.aiter_lines():
                        if line.startswith("data: ") and line != "data: [DONE]":
                            try:
                                chunk = json.loads(line[6:])
                                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                                if delta:
                                    full_text += delta
                            except json.JSONDecodeError:
                                pass
                return full_text, None, None
            else:
                resp = await client.post(url, headers=headers, json=data)
                if resp.status_code != 200:
                    err_data = resp.json() if resp.content else {}
                    msg = err_data.get("error", {}).get("message", resp.text[:200])
                    return None, None, Exception(f"HTTP {resp.status_code}: {msg}")

                result = resp.json()
                choice = result.get("choices", [{}])[0]
                text = choice.get("message", {}).get("content", "")
                tokens = result.get("usage", {}).get("total_tokens")
                if text and isinstance(text, str) and text.strip():
                    circuit_breaker.record_success(model_key)
                    return text.strip(), tokens, None
                return None, None, Exception("Empty response")
    except httpx.TimeoutException as e:
        circuit_breaker.record_failure(model_key)
        return None, None, e
    except Exception as e:
        circuit_breaker.record_failure(model_key)
        return None, None, e


async def chat_completion(
    messages: List[Dict[str, Any]],
    max_tokens: int = 4000,
    stream: bool = False,
    model_hint: Optional[str] = None,
) -> Tuple[str, str, int]:
    """
    Каскадный вызов: пробует провайдеры по порядку с учётом Circuit Breaker.
    Returns: (text, model_used, tokens)
    """
    providers = _get_providers()
    last_error: Optional[Exception] = None

    for provider in providers:
        models_order = provider.models.copy()
        if model_hint and provider.name == "artemox" and model_hint not in models_order:
            models_order = [model_hint] + [m for m in models_order if m != model_hint]
        elif model_hint and provider.name == "artemox":
            models_order = [model_hint] + [m for m in models_order if m != model_hint]
        for model in models_order:
            model_key = f"{provider.name}:{model}"
            if circuit_breaker.is_open(model_key):
                continue
            try:
                t0 = time.monotonic()
                text, tokens, err = await asyncio.wait_for(
                    _chat_completion_request(
                        provider, model, messages,
                        max_tokens=max_tokens, stream=stream,
                    ),
                    timeout=MODEL_TIMEOUT_SEC + 2,
                )
                duration = time.monotonic() - t0
                if err:
                    last_error = err
                    try:
                        from utils.metrics import record_error, record_request
                        record_request(model_key, status="error")
                        record_error(model_key, type(err).__name__)
                    except Exception:
                        pass
                    logger.warning(f"Cascade skip {model_key}: {err}")
                    continue
                if text:
                    try:
                        from utils.metrics import (
                            record_request,
                            record_response_time,
                            record_tokens,
                        )
                        record_request(model_key, status="success")
                        record_response_time(model_key, duration)
                        if tokens:
                            record_tokens(model_key, tokens)
                    except Exception:
                        pass
                    return text, model_key, tokens or 0
            except asyncio.TimeoutError:
                circuit_breaker.record_failure(model_key)
                last_error = TimeoutError(f"Timeout {MODEL_TIMEOUT_SEC}s for {model_key}")
                logger.warning(str(last_error))
                continue
            except Exception as e:
                last_error = e
                logger.warning(f"Cascade error {model_key}: {e}")
                continue

    raise Exception(last_error or "All providers failed")
