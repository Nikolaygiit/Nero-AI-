"""
RAG (Retrieval-Augmented Generation): PDF → чанки → эмбеддинги → ChromaDB.
При вопросе пользователя ищем похожие фрагменты и подставляем в контекст LLM.
"""

import asyncio
import hashlib
import logging
import re
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import httpx
from pypdf import PdfReader

import config

logger = logging.getLogger(__name__)

# ChromaDB импортируется лениво (синхронный API), вызовы оборачиваем в run_in_executor
_chroma_client = None
_chroma_collection = None

# Параметры чанкинга
CHUNK_SIZE = 600
CHUNK_OVERLAP = 100
MAX_CHUNKS_PER_DOC = 500
RAG_TOP_K = 5
RAG_MIN_SCORE = 0.3


def _get_chroma():
    """Ленивая инициализация ChromaDB (синхронная)."""
    global _chroma_client, _chroma_collection
    if _chroma_collection is not None:
        return _chroma_collection
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
    except ImportError:
        raise RuntimeError("Установите chromadb: pip install chromadb")
    path = Path(config.RAG_CHROMA_PATH)
    path.mkdir(parents=True, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(path=str(path), settings=ChromaSettings(anonymized_telemetry=False))
    _chroma_collection = _chroma_client.get_or_create_collection(
        name="rag_docs",
        metadata={"description": "RAG chunks from user PDFs"},
    )
    return _chroma_collection


async def _embed_texts(texts: List[str]) -> List[List[float]]:
    """Получить эмбеддинги для списка текстов через API (OpenAI-совместимый /embeddings)."""
    if not texts:
        return []
    url = f"{config.GEMINI_API_BASE.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {config.GEMINI_API_KEY}",
        "Content-Type": "application/json",
    }
    # Некоторые API принимают только один input; делаем батчи по 1 для совместимости
    all_embeddings: List[List[float]] = []
    batch_size = 20
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        # Стандарт: input может быть строкой или массивом строк
        body = {
            "model": config.RAG_EMBEDDING_MODEL,
            "input": batch[0] if len(batch) == 1 else batch,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=body)
                if resp.status_code != 200:
                    err = resp.text
                    logger.warning("Embeddings API error: %s", err[:200])
                    raise RuntimeError(f"Embeddings API: {resp.status_code} {err[:200]}")
                data = resp.json()
                items = data.get("data", [])
                if not items:
                    raise RuntimeError("Embeddings API вернул пустой data")
                # Сортируем по index на случай неупорядоченного ответа
                items_sorted = sorted(items, key=lambda x: x.get("index", 0))
                for it in items_sorted:
                    emb = it.get("embedding")
                    if emb is not None:
                        all_embeddings.append(emb)
        except Exception as e:
            logger.exception("Embeddings request failed: %s", e)
            raise
    return all_embeddings


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Разбить текст на перекрывающиеся чанки по символам."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text) and len(chunks) < MAX_CHUNKS_PER_DOC:
        end = start + chunk_size
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start = end - overlap
    return chunks


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """Извлечь текст из PDF."""
    reader = PdfReader(BytesIO(pdf_bytes))
    parts = []
    for page in reader.pages:
        try:
            t = page.extract_text()
            if t:
                parts.append(t)
        except Exception as e:
            logger.warning("Ошибка извлечения страницы PDF: %s", e)
    return "\n".join(parts) if parts else ""


async def add_pdf_document(user_id: int, pdf_bytes: bytes, filename: str) -> tuple[bool, str]:
    """
    Добавить PDF в векторную БД для пользователя.
    Возвращает (success, message).
    """
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, _pdf_to_text, pdf_bytes)
    if not text or len(text.strip()) < 50:
        return False, "В PDF мало текста или он не извлечён. Попробуйте другой файл."

    chunks = _chunk_text(text)
    if not chunks:
        return False, "Не удалось разбить документ на фрагменты."

    try:
        embeddings = await _embed_texts(chunks)
    except Exception as e:
        logger.exception("RAG embeddings failed: %s", e)
        return False, f"Ошибка эмбеддингов (проверьте, что API поддерживает /embeddings): {e!s}"

    if len(embeddings) != len(chunks):
        return False, "Ошибка: число эмбеддингов не совпадает с числом чанков."

    doc_id = hashlib.sha256(pdf_bytes[:8192]).hexdigest()[:16]
    collection = await loop.run_in_executor(None, _get_chroma)
    user_str = str(user_id)
    ids = [f"{user_str}_{doc_id}_{i}" for i in range(len(chunks))]
    metadatas = [{"user_id": user_str, "doc_name": filename[:200], "chunk_idx": i} for i in range(len(chunks))]

    def _add():
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )

    await loop.run_in_executor(None, _add)
    logger.info("RAG: added document user_id=%s filename=%s chunks=%s", user_id, filename, len(chunks))
    return True, f"Документ «{filename}» добавлен. Фрагментов: {len(chunks)}. Можете задавать вопросы по нему."


async def get_rag_context(user_id: int, query: str, top_k: int = RAG_TOP_K) -> Optional[str]:
    """
    Найти релевантные фрагменты по запросу пользователя.
    Возвращает один блок текста для вставки в промпт или None.
    """
    if not query or len(query.strip()) < 2:
        return None
    loop = asyncio.get_event_loop()
    try:
        q_embeddings = await _embed_texts([query.strip()])
    except Exception as e:
        logger.warning("RAG query embedding failed: %s", e)
        return None
    if not q_embeddings:
        return None

    collection = await loop.run_in_executor(None, _get_chroma)

    def _query():
        return collection.query(
            query_embeddings=q_embeddings,
            n_results=top_k,
            where={"user_id": str(user_id)},
            include=["documents", "metadatas", "distances"],
        )

    result = await loop.run_in_executor(None, _query)
    if not result or not result.get("documents") or not result["documents"][0]:
        return None
    docs = result["documents"][0]
    distances = result.get("distances", [[]])[0] if result.get("distances") else []
    # ChromaDB по умолчанию L2: меньше = ближе. Нормализуем в условную «релевантность»
    chosen = []
    for i, doc in enumerate(docs):
        distances[i] if i < len(distances) else 0
        # Простой порог: если расстояние очень большое, не брать (зависит от метрики)
        chosen.append(doc)
    if not chosen:
        return None
    context = "\n\n---\n\n".join(chosen[:top_k])
    return f"Контекст из загруженных документов:\n\n{context}\n\nОтвечай на вопрос пользователя, опираясь в первую очередь на этот контекст. Если в контексте нет ответа — скажи об этом."


async def has_rag_documents(user_id: int) -> bool:
    """Проверить, есть ли у пользователя хотя бы один документ в RAG."""
    loop = asyncio.get_event_loop()
    collection = await loop.run_in_executor(None, _get_chroma)

    def _count():
        r = collection.get(where={"user_id": str(user_id)}, include=[])
        return len(r["ids"]) > 0

    return await loop.run_in_executor(None, _count)


async def list_rag_documents(user_id: int) -> List[str]:
    """Вернуть список имён документов пользователя (уникальные doc_name)."""
    loop = asyncio.get_event_loop()
    collection = await loop.run_in_executor(None, _get_chroma)

    def _get():
        r = collection.get(where={"user_id": str(user_id)}, include=["metadatas"])
        names = set()
        for m in r.get("metadatas") or []:
            if m and isinstance(m, dict):
                n = m.get("doc_name")
                if n:
                    names.add(n)
        return list(names)

    return await loop.run_in_executor(None, _get)


async def clear_rag_documents(user_id: int) -> int:
    """Удалить все чанки пользователя. Возвращает количество удалённых id."""
    loop = asyncio.get_event_loop()
    collection = await loop.run_in_executor(None, _get_chroma)

    def _get_ids():
        r = collection.get(where={"user_id": str(user_id)}, include=[])
        return r.get("ids") or []

    ids = await loop.run_in_executor(None, _get_ids)
    if not ids:
        return 0

    def _delete():
        collection.delete(ids=ids)

    await loop.run_in_executor(None, _delete)
    logger.info("RAG: cleared user_id=%s count=%s", user_id, len(ids))
    return len(ids)
