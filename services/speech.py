"""
Speech: Whisper (STT) и TTS через Artemox/Gemini
"""

import logging
from typing import Optional

import httpx

import config

logger = logging.getLogger(__name__)


async def speech_to_text(voice_bytes: bytes, lang: str = "ru") -> Optional[str]:
    """
    Распознавание речи (Whisper) через OpenAI или Artemox.
    """
    api_key = config.settings.OPENAI_API_KEY or config.GEMINI_API_KEY
    api_base = "https://api.openai.com/v1" if config.settings.OPENAI_API_KEY else config.GEMINI_API_BASE
    url = f"{api_base.rstrip('/')}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {"file": ("voice.ogg", voice_bytes, "audio/ogg")}
    data = {"model": "whisper-1", "language": lang}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            if resp.status_code == 200:
                j = resp.json()
                return j.get("text", "").strip()
    except Exception as e:
        logger.warning("Whisper STT failed: %s", e)
    return None


async def text_to_speech(text: str, lang: str = "ru") -> Optional[bytes]:
    """
    TTS через Gemini (если доступен) или заглушка.
    """
    url = f"{config.GEMINI_API_BASE}/audio/speech"
    headers = {
        "Authorization": f"Bearer {config.GEMINI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": "tts-1", "input": text, "voice": "alloy"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                return resp.content
    except Exception as e:
        logger.debug("TTS failed: %s", e)
    return None
