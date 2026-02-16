"""
Prometheus-метрики для Observability
requests_per_minute, average_response_time, errors_count, token_usage
HTTP: /metrics (Prometheus), /health (liveness для балансировщиков и оркестраторов).
"""

import threading
import time
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import AsyncGenerator

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Histogram,
        generate_latest,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    CONTENT_TYPE_LATEST = ""  # type: ignore[assignment]
    REGISTRY = None  # type: ignore[assignment]

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
    REQUESTS_TOTAL = None  # type: ignore[assignment]
    RESPONSE_TIME = None  # type: ignore[assignment]
    TOKENS_USED = None  # type: ignore[assignment]
    ERRORS_TOTAL = None  # type: ignore[assignment]


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
    """Запустить HTTP-сервер: GET /health -> 200 JSON, GET /metrics -> Prometheus."""
    if not PROMETHEUS_AVAILABLE:
        return

    class _MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (required by BaseHTTPRequestHandler)
            path = self.path.rstrip("/") or "/"
            if path == "/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
                return
            if path == "/metrics":
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE_LATEST)
                self.end_headers()
                self.wfile.write(generate_latest(REGISTRY))
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A002
            pass  # уменьшить шум в логах

    server = HTTPServer(("", port), _MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


def get_metrics_payload() -> bytes:
    """Получить сырые метрики в формате Prometheus (для /metrics endpoint)"""
    if PROMETHEUS_AVAILABLE:
        return generate_latest(REGISTRY)
    return b"# prometheus_client not installed\n"
