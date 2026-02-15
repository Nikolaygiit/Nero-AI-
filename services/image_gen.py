"""
Сервис генерации изображений с паттерном Strategy и очередью
"""
import asyncio
import base64
import logging
from abc import ABC, abstractmethod
from typing import Optional, Tuple

import httpx

import config
from database import db

logger = logging.getLogger(__name__)

# Счётчик активных генераций (для отображения позиции в очереди)
_active_generations = 0
_gen_lock = asyncio.Lock()


class ImageGeneratorStrategy(ABC):
    """Абстрактный класс для стратегий генерации изображений"""

    @abstractmethod
    async def generate(self, prompt: str, style: Optional[str] = None, size: Optional[str] = None, image: Optional[str] = None) -> bytes:
        """Генерировать изображение"""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Получить название стратегии"""
        pass


class ArtemoxImageGenerator(ImageGeneratorStrategy):
    """Генерация изображений через Artemox API (Imagen/Gemini Image)"""

    def __init__(self, api_key: str = None, api_base: str = None):
        self.api_key = api_key or config.GEMINI_API_KEY
        self.api_base = api_base or config.GEMINI_API_BASE

    def get_name(self) -> str:
        return "Artemox (Imagen/Gemini Image)"

    async def generate(self, prompt: str, style: Optional[str] = None, size: Optional[str] = None, image: Optional[str] = None) -> bytes:
        """Генерировать изображение через Artemox API"""

        # Применяем стиль к промпту
        if style and style in config.IMAGE_STYLES:
            prompt = f"{prompt}, {config.IMAGE_STYLES[style].lower()} style"

        # Получаем размер
        image_size = config.IMAGE_SIZES.get(size, '1024x1024') if size else '1024x1024'

        # Модели для генерации изображений (приоритет по качеству)
        models_to_try = [
            'gemini-3-pro-image-preview',
            'imagen-4.0-ultra-generate-001',
            'imagen-4.0-generate-001',
            'imagen-4.0-fast-generate-001',
            'gemini-2.5-flash-image-preview',
            'imagen-3.0-generate-002',
            'imagen-3.0-generate-001',
            'imagen-3.0-fast-generate-001',
            'gemini-2.5-flash-image',
        ]

        url = f"{self.api_base}/images/generations"
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        last_error = None

        async with httpx.AsyncClient(timeout=90.0) as client:
            for model_name in models_to_try:
                try:
                    # Формируем данные запроса
                    data = {
                        "model": model_name,
                        "prompt": prompt,
                        "n": 1,
                        "size": image_size,
                        "response_format": "b64_json"
                    }

                    if image:
                        data["image"] = image

                    response = await client.post(url, headers=headers, json=data)

                    if response.status_code == 200:
                        result = response.json()

                        # Проверяем разные форматы ответа
                        if 'data' in result and len(result['data']) > 0:
                            image_data = result['data'][0]
                            # Может быть 'b64_json' или 'url'
                            if 'b64_json' in image_data:
                                return base64.b64decode(image_data['b64_json'])
                            elif 'url' in image_data:
                                # Если URL, скачиваем изображение
                                img_response = await client.get(image_data['url'])
                                img_response.raise_for_status()
                                return img_response.content

                        # Альтернативный формат ответа
                        if 'image' in result:
                            if isinstance(result['image'], str):
                                return base64.b64decode(result['image'])
                            elif isinstance(result['image'], bytes):
                                return result['image']

                    if response.status_code == 429:
                        logger.warning(f"Rate limit для {model_name}")
                        continue
                    elif response.status_code == 404:
                        logger.debug(f"Модель {model_name} не найдена")
                        continue
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
        error_msg = last_error or "Не удалось сгенерировать изображение"
        raise Exception(f"{error_msg}. Проверьте доступность моделей генерации изображений.")


class ImageGenerator:
    """Основной класс для генерации изображений с fallback стратегиями"""

    def __init__(self):
        self.strategies: list[ImageGeneratorStrategy] = [
            ArtemoxImageGenerator(),  # Основная стратегия
        ]

    async def generate(
        self,
        prompt: str,
        user_id: Optional[int] = None,
        style: Optional[str] = None,
        size: Optional[str] = None,
        image: Optional[str] = None
    ) -> Tuple[bytes, str]:
        """
        Генерировать изображение, пробуя разные стратегии

        Returns:
            Tuple[bytes, str]: (изображение, название использованной стратегии)
        """
        last_error = None

        for strategy in self.strategies:
            try:
                logger.info(f"Попытка генерации через {strategy.get_name()}")
                image_bytes = await strategy.generate(prompt, style, size, image)

                # Обновляем статистику
                if user_id:
                    await db.update_stats(user_id, images_generated=1)

                logger.info(f"✅ Изображение успешно сгенерировано через {strategy.get_name()}")
                return image_bytes, strategy.get_name()

            except Exception as e:
                logger.warning(f"Стратегия {strategy.get_name()} не сработала: {e}")
                last_error = str(e)
                continue

        # Если все стратегии не сработали
        error_msg = last_error or "Все методы генерации недоступны"
        raise Exception(f"Не удалось сгенерировать изображение. {error_msg}")


# Глобальный экземпляр генератора изображений
image_generator = ImageGenerator()


async def get_queue_position() -> int:
    """Возвращает количество активных генераций + 1 (позиция нового запроса)"""
    async with _gen_lock:
        return _active_generations + 1


async def generate_with_queue(prompt: str, user_id: int, style: Optional[str] = None, size: Optional[str] = None, image: Optional[str] = None) -> Tuple[bytes, str]:
    """
    Генерация с отображением позиции в очереди.
    """
    global _active_generations
    async with _gen_lock:
        _active_generations += 1

    try:
        return await image_generator.generate(prompt, user_id, style, size, image)
    finally:
        async with _gen_lock:
            _active_generations = max(0, _active_generations - 1)
