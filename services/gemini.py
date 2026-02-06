"""
Асинхронный сервис для работы с Gemini API через Artemox
"""
import httpx
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import config
from database import db

logger = logging.getLogger(__name__)

# Кэш для доступных моделей
available_models_cache: List[str] = []
current_model_name: str = ""


class GeminiService:
    """Сервис для работы с Gemini API через Artemox"""
    
    def __init__(self, api_key: str = None, api_base: str = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.api_base = api_base or config.GEMINI_API_BASE
        self.client = None
    
    async def __aenter__(self):
        """Асинхронный контекстный менеджер - вход"""
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=30.0),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
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
        
        url = f"{self.api_base}/models"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                models = [model['id'] for model in data.get('data', [])]
                available_models_cache = models
                logger.info(f"Найдено {len(models)} доступных моделей")
                return models
        except Exception as e:
            logger.error(f"Ошибка получения списка моделей: {e}")
            # Возвращаем модели по умолчанию
            return config.PREFERRED_MODELS[:5]
    
    async def generate_content(
        self,
        prompt: str,
        user_id: Optional[int] = None,
        use_context: bool = True,
        model: Optional[str] = None
    ) -> str:
        """
        Генерация контента через Gemini API
        
        Args:
            prompt: Текст запроса
            user_id: ID пользователя для контекста
            use_context: Использовать ли историю диалога
            model: Конкретная модель (если None - выбирается автоматически)
        
        Returns:
            Сгенерированный текст
        """
        global current_model_name
        
        # Получаем доступные модели
        available_models = await self.list_available_models()
        
        # Получаем контекст и настройки
        context_messages = []
        persona_prompt = config.PERSONAS['assistant']['prompt']
        
        if user_id and use_context:
            # Получаем историю из базы данных
            messages = await db.get_user_messages(user_id, limit=10)
            context_messages = [
                {"role": msg.role, "content": msg.content}
                for msg in messages
            ]
            
            # Получаем настройки пользователя
            user = await db.get_user(user_id)
            if user:
                persona_key = user.persona or 'assistant'
                persona_prompt = config.PERSONAS.get(persona_key, config.PERSONAS['assistant'])['prompt']
        
        # Формируем системное сообщение
        system_prompt = f"{persona_prompt}\n\nВажно: Отвечай на русском языке. Будь естественным и понятным."
        
        # Формируем сообщения для API
        messages = [{"role": "system", "content": system_prompt}]
        
        # Добавляем контекст
        for msg in context_messages[-10:]:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })
        
        # Текущий запрос
        messages.append({"role": "user", "content": prompt})
        
        # Выбираем модели для попыток
        models_to_try = []
        if model:
            models_to_try = [model]
        elif available_models:
            # Приоритет моделям из конфига
            for preferred in config.PREFERRED_MODELS:
                for available in available_models:
                    if preferred == available or (preferred in available and available not in models_to_try):
                        models_to_try.append(available)
                        break
            if not models_to_try:
                models_to_try = available_models[:5]
        else:
            models_to_try = config.PREFERRED_MODELS[:5]
        
        url = f"{self.api_base}/chat/completions"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        last_error = None
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            for model_name in models_to_try:
                try:
                    data = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": config.MAX_TOKENS_PER_REQUEST
                    }
                    
                    response = await client.post(url, headers=headers, json=data)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if 'choices' in result and len(result['choices']) > 0:
                            choice = result['choices'][0]
                            if 'message' in choice and 'content' in choice['message']:
                                text = choice['message']['content']
                                if text and isinstance(text, str) and text.strip():
                                    current_model_name = model_name
                                    
                                    # Сохраняем сообщения в базу данных
                                    if user_id:
                                        await db.add_message(user_id, "user", prompt)
                                        await db.add_message(user_id, "assistant", text.strip())
                                        
                                        # Обновляем статистику
                                        tokens = result.get('usage', {}).get('total_tokens', 0)
                                        await db.update_stats(
                                            user_id,
                                            requests_count=1,
                                            tokens_used=tokens
                                        )
                                        
                                        # Получаем пользователя для проверки ID
                                        user = await db.get_user(user_id)
                                        if not user:
                                            # Создаем пользователя, если его нет
                                            await db.create_or_update_user(telegram_id=user_id)
                                    
                                    return text.strip()
                    
                    if response.status_code == 429:
                        logger.warning(f"Rate limit для {model_name}")
                        continue
                    elif response.status_code == 401:
                        error_data = response.json() if response.content else {}
                        error_msg = error_data.get('error', {}).get('message', 'Неверный API ключ')
                        raise Exception(f"Неверный API ключ: {error_msg[:100]}")
                    else:
                        error_data = response.json() if response.content else {}
                        error_msg = error_data.get('error', {}).get('message', f'HTTP {response.status_code}')
                        last_error = error_msg
                        logger.warning(f"Ошибка {response.status_code} для {model_name}: {error_msg}")
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
        
        # Если все модели не сработали
        error_msg = last_error or "Не удалось получить ответ от API"
        raise Exception(f"{error_msg}. Проверьте подключение к интернету и правильность API ключа.")
    
    async def analyze_image(
        self,
        image_base64: str,
        prompt: str = "Опиши это изображение подробно на русском языке",
        user_id: Optional[int] = None
    ) -> str:
        """
        Анализ изображения через Gemini Vision
        
        Args:
            image_base64: Изображение в формате base64
            prompt: Текст запроса для анализа
            user_id: ID пользователя
        
        Returns:
            Текст анализа изображения
        """
        available_models = await self.list_available_models()
        
        # Ищем модели с поддержкой vision
        vision_models = [
            m for m in available_models
            if any(x in m.lower() for x in ['flash', 'pro', '1.5', '2.0', '2.5', '3.0'])
        ]
        
        if not vision_models:
            vision_models = config.PREFERRED_MODELS[:3]
        
        url = f"{self.api_base}/chat/completions"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        # Формируем сообщение с изображением
        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                }
            ]
        }]
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            for model_name in vision_models[:3]:  # Пробуем первые 3 модели
                try:
                    data = {
                        "model": model_name,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": config.MAX_TOKENS_PER_REQUEST
                    }
                    
                    response = await client.post(url, headers=headers, json=data)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if 'choices' in result and len(result['choices']) > 0:
                            text = result['choices'][0]['message']['content']
                            if text and isinstance(text, str) and text.strip():
                                # Сохраняем в базу данных
                                if user_id:
                                    await db.add_message(user_id, "user", f"[Изображение] {prompt}")
                                    await db.add_message(user_id, "assistant", text.strip())
                                
                                return text.strip()
                    
                    logger.warning(f"Модель {model_name} не подошла для анализа изображения")
                    continue
                    
                except Exception as e:
                    logger.error(f"Ошибка анализа изображения через {model_name}: {e}")
                    continue
        
        raise Exception("Не удалось проанализировать изображение. Попробуйте другую модель.")


# Глобальный экземпляр сервиса
gemini_service = GeminiService()
