"""
Тесты для services.rag: _embed_texts, _chunk_text (с моками httpx/config).
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.modules["config"] = MagicMock()
mock_config = sys.modules["config"]
mock_config.GEMINI_API_BASE = "https://api.test/v1"
mock_config.GEMINI_API_KEY = "key"
mock_config.RAG_EMBEDDING_MODEL = "text-embedding-001"

if "services.rag" in sys.modules:
    del sys.modules["services.rag"]
from services import rag  # noqa: E402, I001


# --- _chunk_text (чистая функция, без моков) ---


class TestChunkText:
    def test_empty_string(self):
        assert rag._chunk_text("") == []
        assert rag._chunk_text("   ") == []

    def test_short_text_one_chunk(self):
        text = "Hello world"
        chunks = rag._chunk_text(text, chunk_size=100, overlap=10)
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_long_text_multiple_chunks(self):
        text = "a" * 1000
        chunks = rag._chunk_text(text, chunk_size=200, overlap=50)
        assert len(chunks) >= 4
        assert all(len(c) <= 200 for c in chunks)
        joined = "".join(chunks).replace(" ", "")
        assert len(joined) >= 900


# --- _embed_texts (мок httpx) ---


@pytest.mark.asyncio
async def test_embed_texts_empty():
    result = await rag._embed_texts([])
    assert result == []


@pytest.mark.asyncio
async def test_embed_texts_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"index": 0, "embedding": [0.1] * 10},
        ],
    }
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.rag.httpx.AsyncClient", return_value=mock_client):
        result = await rag._embed_texts(["hello"])

    assert len(result) == 1
    assert len(result[0]) == 10
    assert result[0][0] == 0.1


@pytest.mark.asyncio
async def test_embed_texts_batch_two():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {"index": 0, "embedding": [0.0] * 5},
            {"index": 1, "embedding": [1.0] * 5},
        ],
    }
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.rag.httpx.AsyncClient", return_value=mock_client):
        result = await rag._embed_texts(["a", "b"])

    assert len(result) == 2
    assert result[0] == [0.0] * 5
    assert result[1] == [1.0] * 5


@pytest.mark.asyncio
async def test_embed_texts_http_error_raises():
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.rag.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(RuntimeError) as exc_info:
            await rag._embed_texts(["hello"])
    assert "401" in str(exc_info.value) or "Unauthorized" in str(exc_info.value)
