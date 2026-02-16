"""
Асинхронный сервис для работы с Gemini API через Artemox.
Единая точка входа для генерации текста (generate_content / stream) и vision (изображения).
"""

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

import config
from database import db
from services.llm_common import (
    DEFAULT_REQUEST_TIMEOUT,
    build_chat_url,
    build_headers,
    llm_semaphore,
)

logger = logging.getLogger(__name__)
try:
    import structlog

    struct_log = structlog.get_logger(__name__)
except ImportError:
    struct_log = None

# Кэш для доступных моделей
available_models_cache: List[str] = []
current_model_name: str = ""


class GeminiService:
    """Сервис для работы с Gemini API через Artemox"""

    def __init__(self, api_key: str = None, api_base: str = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.api_base = api_base or config.GEMINI_API_BASE
        self.client = None

    def _chat_url(self) -> str:
        return build_chat_url(self.api_base)

    def _headers(self) -> Dict[str, str]:
        return build_headers(self.api_key)

    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(DEFAULT_REQUEST_TIMEOUT, connect=30.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Асинхронный контекстный менеджер - выход"""
        if self.client:
            await self.client.aclose()

    async def list_available_models(self) -> List[str]:
        """Получить список доступных моделей"""
        global available_models_cache

        if available_models_cache:
            return available_models_cache

        url = f"{self.api_base.rstrip('/')}/models"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._headers())
                response.raise_for_status()

                data = response.json()
                models = [model["id"] for model in data.get("data", [])]
                available_models_cache = models
                logger.info(f"Найдено {len(models)} доступных моделей")
                return models
        except Exception as e:
            logger.error(f"Ошибка получения списка моделей: {e}")
            # Возвращаем модели по умолчанию
            return config.PREFERRED_MODELS[:5]

    async def _prepare_messages_context(
        self,
        prompt: str,
        user_id: Optional[int],
        use_context: bool,
        rag_context: Optional[str] = None,
        *,
        history_limit: int = 10,
        extra_system: str = "",
    ) -> List[Dict[str, Any]]:
        """Единая подготовка контекста и сообщений для текстовой генерации."""
        context_messages = []
        persona_prompt = config.PERSONAS["assistant"]["prompt"]

        if user_id and use_context:
            messages = await db.get_user_messages(user_id, limit=history_limit)
            context_messages = [{"role": msg.role, "content": msg.content} for msg in messages]
            # Обрезка по лимиту символов (старые сообщения убираются)
            max_chars = getattr(config, "MAX_CONTEXT_CHARS", 12000)
            while (
                context_messages
                and sum(len(m.get("content", "") or "") for m in context_messages) > max_chars
            ):
                context_messages.pop(0)
            user = await db.get_user(user_id)
            if user:
                persona_key = user.persona or "assistant"
                persona_prompt = config.PERSONAS.get(persona_key, config.PERSONAS["assistant"])[
                    "prompt"
                ]

        from services.memory import get_relevant_facts

        facts_block = await get_relevant_facts(user_id) if user_id else ""
        facts_line = f"\n\n{facts_block}" if facts_block else ""
        rag_block = f"\n\n{rag_context}" if rag_context else ""
        system_prompt = (
            f"{persona_prompt}{facts_line}{rag_block}\n\n"
            f"Важно: Отвечай на русском языке. Будь естественным и понятным.{extra_system}"
        )

        messages = [{"role": "system", "content": system_prompt}]
        for msg in context_messages[-history_limit:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def _select_target_models(self, model_hint: Optional[str]) -> List[str]:
        """Select models to try based on hint and availability"""
        available_models = await self.list_available_models()
        models_to_try = []

        if model_hint:
            models_to_try = [model_hint]
        elif available_models:
            # Приоритет моделям из конфига
            for preferred in config.PREFERRED_MODELS:
                for available in available_models:
                    if preferred == available or (
                        preferred in available and available not in models_to_try
                    ):
                        models_to_try.append(available)
                        break
            if not models_to_try:
                models_to_try = available_models[:5]
        else:
            models_to_try = config.PREFERRED_MODELS[:5]

        return models_to_try

    async def _handle_interaction_success(
        self, user_id: Optional[int], prompt: str, response_text: str, tokens: int, model_name: str
    ):
        """Handle successful interaction: save to DB, update stats"""
        global current_model_name
        current_model_name = model_name

        if user_id:
            await db.add_message(user_id, "user", prompt)
            await db.add_message(user_id, "assistant", response_text)

            await db.update_stats(user_id, requests_count=1, tokens_used=tokens)

            user = await db.get_user(user_id)
            if not user:
                await db.create_or_update_user(telegram_id=user_id)

    async def _execute_legacy_fallback(
        self,
        messages: List[Dict[str, Any]],
        models_to_try: List[str],
        prompt: str,
        user_id: Optional[int],
    ) -> str:
        """Резервный цикл по моделям при недоступности cascade."""
        url = self._chat_url()
        headers = self._headers()
        from services.llm_common import MODEL_TIMEOUT_SEC

        last_error = None
        async with llm_semaphore:
            async with httpx.AsyncClient(timeout=float(MODEL_TIMEOUT_SEC)) as client:
                for model_name in models_to_try:
                    try:
                        data = {
                            "model": model_name,
                            "messages": messages,
                            "temperature": 0.7,
                            "max_tokens": config.MAX_TOKENS_PER_REQUEST,
                        }

                        response = None
                        for attempt in range(3):
                            response = await client.post(url, headers=headers, json=data)
                            if response.status_code == 429 and attempt < 2:
                                await asyncio.sleep(2.0 * (attempt + 1))
                                continue
                            break
                        if response is None:
                            continue

                        if response.status_code == 200:
                            result = response.json()
                            if "choices" in result and len(result["choices"]) > 0:
                                choice = result["choices"][0]
                                if "message" in choice and "content" in choice["message"]:
                                    text = choice["message"]["content"]
                                    if text and isinstance(text, str) and text.strip():
                                        tokens = result.get("usage", {}).get("total_tokens", 0)
                                        await self._handle_interaction_success(
                                            user_id, prompt, text.strip(), tokens, model_name
                                        )
                                        return text.strip()

                        if response.status_code == 429:
                            logger.warning(f"Rate limit для {model_name}")
                            continue
                        elif response.status_code == 401:
                            error_data = response.json() if response.content else {}
                            error_msg = error_data.get("error", {}).get(
                                "message", "Неверный API ключ"
                            )
                            raise Exception(f"Неверный API ключ: {error_msg[:100]}")
                        else:
                            error_data = response.json() if response.content else {}
                            error_msg = error_data.get("error", {}).get(
                                "message", f"HTTP {response.status_code}"
                            )
                            last_error = error_msg
                            logger.warning(
                                f"Ошибка {response.status_code} для {model_name}: {error_msg}"
                            )
                            continue

                    except httpx.TimeoutException:
                        logger.warning(f"Таймаут для {model_name}")
                        continue
                    except httpx.HTTPError as e:
                        logger.error(f"Ошибка HTTP для {model_name}: {e}")
                        last_error = str(e)
                        continue
                    except Exception as e:
                        logger.error(f"Ошибка для {model_name}: {e}")
                        last_error = str(e)
                        continue

        error_msg = last_error or "Не удалось получить ответ от API"
        raise Exception(f"{error_msg}. Проверьте подключение к интернету и правильность API ключа.")

    async def generate_content(
        self,
        prompt: str,
        user_id: Optional[int] = None,
        use_context: bool = True,
        model: Optional[str] = None,
        rag_context: Optional[str] = None,
    ) -> str:
        """
        Генерация контента через Gemini API (cascade + legacy fallback).

        Args:
            prompt: Текст запроса
            user_id: ID пользователя для контекста и истории
            use_context: Использовать ли историю диалога и персона
            model: Конкретная модель (если None — выбор по приоритету)
            rag_context: Текст из RAG (PDF) для вставки в системный промпт

        Returns:
            Сгенерированный текст
        """
        t0 = time.perf_counter()
        messages = await self._prepare_messages_context(prompt, user_id, use_context, rag_context)
        msg_chars = sum(len(m.get("content", "") or "") for m in messages)
        if struct_log:
            struct_log.info(
                "generate_content_start",
                model_hint=model,
                prompt_len=len(prompt),
                messages_chars=msg_chars,
                user_id=user_id,
            )

        # 2. Try Cascade (Circuit Breaker)
        try:
            from services.llm_cascade import chat_completion

            text, model_used, tokens = await chat_completion(
                messages=messages,
                max_tokens=config.MAX_TOKENS_PER_REQUEST,
                stream=False,
                model_hint=model,
            )
            await self._handle_interaction_success(user_id, prompt, text, tokens, model_used)
            if struct_log:
                struct_log.info(
                    "generate_content_ok",
                    model_used=model_used,
                    response_len=len(text),
                    duration_ms=round((time.perf_counter() - t0) * 1000),
                    source="cascade",
                )
            return text
        except Exception as cascade_err:
            logger.warning(f"Cascade failed, trying legacy loop: {cascade_err}")
            pass

        # 3. Fallback to legacy loop
        models_to_try = await self._select_target_models(model)
        text = await self._execute_legacy_fallback(messages, models_to_try, prompt, user_id)
        if struct_log:
            struct_log.info(
                "generate_content_ok",
                response_len=len(text),
                duration_ms=round((time.perf_counter() - t0) * 1000),
                source="legacy",
            )
        return text

    def _parse_stream_delta(self, line: str) -> str:
        """Извлечь текстовый delta из строки SSE."""
        if not line.startswith("data: ") or line == "data: [DONE]":
            return ""
        try:
            chunk = json.loads(line[6:])
            return chunk.get("choices", [{}])[0].get("delta", {}).get("content", "") or ""
        except json.JSONDecodeError:
            return ""

    async def generate_content_stream(
        self,
        prompt: str,
        user_id: Optional[int] = None,
        use_context: bool = True,
        model: Optional[str] = None,
        rag_context: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Потоковая генерация текста — обновление сообщения по мере получения токенов.
        Использует общий _prepare_messages_context и _select_target_models.
        """
        messages = await self._prepare_messages_context(prompt, user_id, use_context, rag_context)
        models_to_try = await self._select_target_models(model)

        url = self._chat_url()
        headers = self._headers()
        full_text = ""

        async with llm_semaphore:
            async with httpx.AsyncClient(timeout=DEFAULT_REQUEST_TIMEOUT) as client:
                for model_name in models_to_try:
                    try:
                        data = {
                            "model": model_name,
                            "messages": messages,
                            "temperature": 0.7,
                            "max_tokens": config.MAX_TOKENS_PER_REQUEST,
                            "stream": True,
                        }
                        async with client.stream(
                            "POST", url, headers=headers, json=data
                        ) as response:
                            if response.status_code != 200:
                                continue
                            async for line in response.aiter_lines():
                                delta = self._parse_stream_delta(line)
                                if delta:
                                    full_text += delta
                                    yield delta
                        if full_text and user_id:
                            await self._handle_interaction_success(
                                user_id, prompt, full_text.strip(), 0, model_name
                            )
                        return
                    except Exception as e:
                        logger.warning("stream_error", model=model_name, error=str(e))
                        continue

        if not full_text:
            text = await self.generate_content(
                prompt,
                user_id=user_id,
                use_context=use_context,
                model=model,
                rag_context=rag_context,
            )
            yield text

    async def _get_vision_models(self) -> List[str]:
        """Список моделей с поддержкой vision (flash, pro, 1.5, 2.0, 2.5, 3.0)."""
        available = await self.list_available_models()
        keywords = ["flash", "pro", "1.5", "2.0", "2.5", "3.0"]
        vision = [m for m in available if any(x in m.lower() for x in keywords)]
        return vision[:5] or config.PREFERRED_MODELS[:3]

    def _user_content_with_image(self, prompt: str, image_base64: str) -> List[Dict[str, Any]]:
        """Контент сообщения user: текст + изображение (multimodal)."""
        return [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
            },
        ]

    async def _prepare_vision_messages(
        self,
        prompt: str,
        image_base64: str,
        user_id: Optional[int],
        use_context: bool,
        *,
        extra_system: str = " Учитывай изображение в контексте.",
    ) -> List[Dict[str, Any]]:
        """Сообщения для vision-запроса: системный контекст (опционально) + user с картинкой."""
        if not user_id or not use_context:
            return [
                {"role": "user", "content": self._user_content_with_image(prompt, image_base64)}
            ]

        base = await self._prepare_messages_context(
            prompt,
            user_id,
            use_context=True,
            rag_context=None,
            history_limit=8,
            extra_system=extra_system,
        )
        # В base последний элемент — user с текстом prompt; заменяем на мультимодальный
        out = base[:-1]
        out.append({"role": "user", "content": self._user_content_with_image(prompt, image_base64)})
        return out

    async def _execute_vision_request(
        self,
        messages: List[Dict[str, Any]],
        user_id: Optional[int],
        prompt_for_db: str,
    ) -> str:
        """Общий цикл POST по vision-моделям; при успехе сохраняет в БД и возвращает текст."""
        vision_models = await self._get_vision_models()
        url = self._chat_url()
        headers = self._headers()

        async with llm_semaphore:
            async with httpx.AsyncClient(timeout=DEFAULT_REQUEST_TIMEOUT) as client:
                for model_name in vision_models[:3]:
                    try:
                        data = {
                            "model": model_name,
                            "messages": messages,
                            "temperature": 0.7,
                            "max_tokens": config.MAX_TOKENS_PER_REQUEST,
                        }
                        response = await client.post(url, headers=headers, json=data)
                        if response.status_code != 200:
                            continue
                        result = response.json()
                        choice = result.get("choices", [{}])[0]
                        text = (choice.get("message") or {}).get("content", "")
                        if text and isinstance(text, str) and text.strip():
                            if user_id:
                                await db.add_message(user_id, "user", prompt_for_db)
                                await db.add_message(user_id, "assistant", text.strip())
                            return text.strip()
                    except Exception as e:
                        logger.warning("vision_request_error", model=model_name, error=str(e))
                        continue

        return ""

    async def generate_with_image_context(
        self,
        prompt: str,
        image_base64: str,
        user_id: Optional[int] = None,
        use_context: bool = True,
    ) -> str:
        """Мультимодальный диалог: ответ на вопрос о ранее отправленном изображении."""
        messages = await self._prepare_vision_messages(prompt, image_base64, user_id, use_context)
        text = await self._execute_vision_request(messages, user_id, f"[Изображение] {prompt}")
        return text or "Не удалось обработать изображение. Попробуйте ещё раз."

    async def analyze_image(
        self,
        image_base64: str,
        prompt: str = "Опиши это изображение подробно на русском языке",
        user_id: Optional[int] = None,
    ) -> str:
        """Анализ изображения через Gemini Vision. Сохраняет ответ в историю при user_id."""
        messages = await self._prepare_vision_messages(
            prompt, image_base64, user_id, use_context=False, extra_system=""
        )
        text = await self._execute_vision_request(messages, user_id, f"[Изображение] {prompt}")
        if not text:
            raise Exception("Не удалось проанализировать изображение. Попробуйте другую модель.")
        return text


# Глобальный экземпляр сервиса
gemini_service = GeminiService()
