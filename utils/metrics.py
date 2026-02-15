"""
Prometheus-метрики для Observability
requests_per_minute, average_response_time, errors_count, token_usage
"""
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

try:
    from prometheus_client import (
        REGISTRY,
        Counter,
        Histogram,
        generate_latest,
        start_http_server,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

if PROMETHEUS_AVAILABLE:
    REQUESTS_TOTAL = Counter(
        "llm_requests_total",
        "Total LLM API requests",
        ["provider", "model", "status"],
    )
    RESPONSE_TIME = Histogram(
        "llm_response_time_seconds",
        "LLM response time in seconds",
        ["provider", "model"],
        buckets=(0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 20.0, 60.0),
    )
    TOKENS_USED = Counter(
        "llm_tokens_total",
        "Total tokens used",
        ["provider", "model"],
    )
    ERRORS_TOTAL = Counter(
        "llm_errors_total",
        "Total LLM errors",
        ["provider", "model", "error_type"],
    )
else:
    REQUESTS_TOTAL = None
    RESPONSE_TIME = None
    TOKENS_USED = None
    ERRORS_TOTAL = None


def _parse_model_key(model_key: str) -> tuple:
    """model_key = 'artemox:gemini-2.0-flash' -> ('artemox', 'gemini-2.0-flash')"""
    if ":" in model_key:
        return tuple(model_key.split(":", 1))
    return ("unknown", model_key or "unknown")


def record_request(model_key: str, status: str = "success", tokens: int = 0) -> None:
    """Записать метрику запроса"""
    if not PROMETHEUS_AVAILABLE:
        return
    provider, model = _parse_model_key(model_key)
    REQUESTS_TOTAL.labels(provider=provider, model=model, status=status).inc()
    if tokens:
        TOKENS_USED.labels(provider=provider, model=model).inc(tokens)


def record_error(model_key: str, error_type: str = "unknown") -> None:
    """Записать метрику ошибки"""
    if not PROMETHEUS_AVAILABLE:
        return
    provider, model = _parse_model_key(model_key)
    ERRORS_TOTAL.labels(provider=provider, model=model, error_type=error_type).inc()


def record_tokens(model_key: str, tokens: int) -> None:
    """Записать использование токенов"""
    if not PROMETHEUS_AVAILABLE or tokens <= 0:
        return
    provider, model = _parse_model_key(model_key)
    TOKENS_USED.labels(provider=provider, model=model).inc(tokens)


def record_response_time(model_key: str, duration_sec: float) -> None:
    """Записать время ответа"""
    if not PROMETHEUS_AVAILABLE:
        return
    provider, model = _parse_model_key(model_key)
    RESPONSE_TIME.labels(provider=provider, model=model).observe(duration_sec)


@asynccontextmanager
async def track_llm_call(model_key: str) -> AsyncGenerator[None, None]:
    """Контекстный менеджер для отслеживания LLM вызова"""
    start = time.monotonic()
    try:
        yield
        record_response_time(model_key, time.monotonic() - start)
    except Exception as e:
        record_error(model_key, type(e).__name__)
        raise


def start_metrics_server(port: int = 9090) -> None:
    """Запустить HTTP-сервер метрик (Prometheus scrape)"""
    if PROMETHEUS_AVAILABLE:
        start_http_server(port)
    else:
        pass  # prometheus_client не установлен


def get_metrics_payload() -> bytes:
    """Получить сырые метрики в формате Prometheus (для /metrics endpoint)"""
    if PROMETHEUS_AVAILABLE:
        return generate_latest(REGISTRY)
    return b"# prometheus_client not installed\n"
