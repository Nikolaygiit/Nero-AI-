"""
Аналитика — отправка событий в PostHog/Amplitude
События: started_bot, generated_image, sent_message и т.д.
"""

import logging
from typing import Any, Optional

import httpx

import config

logger = logging.getLogger(__name__)


def track(
    event: str,
    distinct_id: str,
    properties: Optional[dict[str, Any]] = None,
) -> None:
    """Отправить событие в PostHog. Не блокирует, игнорирует ошибки."""
    if not config.settings.POSTHOG_API_KEY:
        return
    try:
        payload = {
            "api_key": config.settings.POSTHOG_API_KEY,
            "event": event,
            "distinct_id": str(distinct_id),
            "properties": properties or {},
        }
        httpx.post(
            f"{config.settings.POSTHOG_HOST}/capture/",
            json=payload,
            timeout=2.0,
        )
    except Exception:
        pass
