"""
Конфигурация бота — валидация через pydantic-settings.
Бот не запустится, если обязательные ключи отсутствуют.
"""

from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки из .env — валидируются при импорте."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Обязательные ключи — без них бот не запустится
    ARTEMOX_API_KEY: str = Field(min_length=1, description="API ключ Artemox (обязательно)")
    TELEGRAM_BOT_TOKEN: str = Field(min_length=1, description="Токен Telegram-бота (обязательно)")

    # Опциональные
    ARTEMOX_API_BASE: str = Field(default="https://api.artemox.com/v1")
    ADMIN_IDS: str = Field(default="", description="ID администраторов через запятую")
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="URL Redis для очередей")
    # PostgreSQL для высокой нагрузки (~80k+ пользователей). Пусто = SQLite (разработка).
    DATABASE_URL: str = Field(
        default="",
        description="postgresql://user:pass@host:5432/dbname — при пустом используется SQLite",
    )
    POSTHOG_API_KEY: str = Field(default="", description="PostHog project API key для аналитики")
    POSTHOG_HOST: str = Field(default="https://us.posthog.com", description="PostHog host")
    OPENAI_API_KEY: str = Field(
        default="", description="OpenAI API key для Whisper (STT), fallback LLM"
    )
    DEEPSEEK_API_KEY: str = Field(default="", description="DeepSeek API key для fallback LLM")
    ADMIN_PANEL_PASSWORD: str = Field(
        default="", description="Пароль для веб-админки (пусто = без защиты)"
    )
    # RAG: путь к ChromaDB, модель эмбеддингов (если API поддерживает /embeddings)
    RAG_CHROMA_PATH: str = Field(
        default="data/chroma", description="Папка для векторной БД ChromaDB"
    )
    RAG_EMBEDDING_MODEL: str = Field(
        default="gemini-embedding-001",
        description="Модель для эмбеддингов (gemini-embedding-001 или text-embedding-004)",
    )
    # Webhooks (вместо polling для high load)
    USE_WEBHOOKS: bool = Field(default=False, description="Использовать webhooks вместо polling")
    WEBHOOK_URL: str = Field(default="", description="Полный URL: https://domain.com/webhook")
    WEBHOOK_PORT: int = Field(default=8443, description="Порт для webhook")
    METRICS_PORT: int = Field(default=9090, description="Порт Prometheus metrics")
    # Лимит одновременных запросов к LLM API (asyncio.Semaphore) — защита от перегрузки при 80k+ пользователей
    MAX_CONCURRENT_LLM_REQUESTS: int = Field(
        default=50, description="Максимум одновременных запросов к LLM"
    )

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return v
        return str(v) if v else ""

    @property
    def admin_ids_list(self) -> List[int]:
        result = []
        for x in self.ADMIN_IDS.split(","):
            x = x.strip()
            if x:
                try:
                    result.append(int(x))
                except ValueError:
                    pass
        return result


# Загружаем и валидируем при старте — без токена и ключей бот сразу сообщит об этом, а не упадёт через час
try:
    settings = Settings()
except Exception as e:
    raise SystemExit(
        "Ошибка конфигурации! Бот не запустится без обязательных переменных.\n"
        "Добавьте в файл .env в корне проекта:\n"
        "  TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather\n"
        "  ARTEMOX_API_KEY=ваш_api_ключ\n"
        f"Детали: {e}"
    )

# Удобные алиасы
GEMINI_API_KEY = settings.ARTEMOX_API_KEY
GEMINI_API_BASE = settings.ARTEMOX_API_BASE
TELEGRAM_BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
ADMIN_IDS: List[int] = settings.admin_ids_list
RAG_CHROMA_PATH = settings.RAG_CHROMA_PATH
RAG_EMBEDDING_MODEL = settings.RAG_EMBEDDING_MODEL

# Модели для текста (чат, ответы)
PREFERRED_MODELS: List[str] = [
    "gemini-2.0-flash",
    "gemini-1.5-flash-8b",
    "gemini-2.0-flash-lite",
    "gemini-2.5-pro-exp-03-25",
    "gemini-1.5-flash",
    "gemini-2.5-pro-preview",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
    "gemini-2.5-flash-lite",
    "gemini-3-pro-preview",
    "gemini-3-flash-preview",
]

# Модели для генерации изображений
IMAGE_GENERATION_MODELS: List[str] = [
    "imagen-3.0-generate-002",
    "imagen-4.0-generate-001",
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-fast-generate-001",
    "imagen-3.0-generate-001",
    "imagen-3.0-fast-generate-001",
    "gemini-2.5-flash-image-preview",
    "gemini-2.5-flash-image",
    "gemini-3-pro-image-preview",
]

# Модели для эмбеддингов (RAG). По умолчанию text-embedding-004, альтернатива: gemini-embedding-001
RAG_EMBEDDING_MODELS_AVAILABLE: List[str] = ["text-embedding-004", "gemini-embedding-001"]

# Circuit Breaker + Model Cascading
MODEL_TIMEOUT_SEC = 10  # таймаут одного запроса (переключение на fallback)
CIRCUIT_FAILURE_THRESHOLD = 3  # после N ошибок модель отключается
CIRCUIT_COOLDOWN_SEC = 60  # на сколько секунд отключать

# Модель для извлечения фактов (лёгкая, быстрая)
FACT_EXTRACTION_MODEL: str = "gemini-2.0-flash"

# Настройки
MAX_HISTORY_LENGTH = 20
MAX_CONTEXT_CHARS = 12000  # макс. символов истории перед обрезкой (старые сообщения убираются)
FREE_DAILY_LIMIT = 10  # бесплатных запросов в день
CACHE_TTL = 3600
MAX_TOKENS_PER_REQUEST = 4000
RATE_LIMIT_PER_USER = 30

# Стили изображений
IMAGE_STYLES = {
    "realistic": "фотореалистичный",
    "anime": "аниме",
    "cartoon": "мультяшный",
    "oil": "масляная живопись",
    "watercolor": "акварель",
    "pencil": "карандашный рисунок",
    "digital": "цифровой арт",
    "3d": "3D рендер",
}

# Размеры изображений
IMAGE_SIZES = {
    "square": "1024x1024",
    "portrait": "1024x1344",
    "landscape": "1344x1024",
    "wide": "1792x1024",
}

# Персонажи
PERSONAS = {
    "teacher": {
        "name": "Учитель",
        "prompt": "Ты опытный учитель с многолетним стажем. Перед ответом глубоко размышляй о том, как лучше объяснить материал ученику.\n\nПроцесс размышления:\n1. Анализируй уровень понимания вопроса пользователем\n2. Определяй ключевые концепции\n3. Продумывай структуру объяснения от простого к сложному\n4. Подбирай примеры и аналогии\n\nОтвечай структурированно, с примерами.",
    },
    "programmer": {
        "name": "Программист",
        "prompt": "Ты опытный программист-консультант. Анализируй задачу с технической точки зрения. Отвечай с примерами кода, объясняя выбор решений.",
    },
    "assistant": {
        "name": "Помощник",
        "prompt": "Ты дружелюбный и эффективный помощник. Кратко и по делу.",
    },
    "creative": {
        "name": "Креативщик",
        "prompt": "Ты креативный помощник с богатым воображением. Генерируй идеи и нестандартные решения.",
    },
    "analyst": {
        "name": "Аналитик",
        "prompt": "Ты аналитик данных. Анализируй данные, выявляй паттерны, формулируй выводы на основе фактов.",
    },
    "translator": {
        "name": "Переводчик",
        "prompt": "Ты профессиональный переводчик. Точно передавай смысл, сохраняя стиль.",
    },
    "writer": {
        "name": "Писатель",
        "prompt": "Ты опытный писатель и редактор. Стилистически выверенные тексты.",
    },
    "scientist": {
        "name": "Ученый",
        "prompt": "Ты ученый-консультант. Научный анализ, факты, доказательства.",
    },
    "business": {
        "name": "Бизнес-консультант",
        "prompt": "Ты бизнес-консультант. Стратегические и тактические рекомендации.",
    },
    "psychologist": {
        "name": "Психолог",
        "prompt": "Ты психолог-консультант. Эмпатично и поддерживающе.",
    },
}

# Достижения
ACHIEVEMENTS_LIST = {
    "first_message": "Первое сообщение",
    "10_messages": "10 сообщений",
    "100_messages": "100 сообщений",
    "first_image": "Первое изображение",
    "10_images": "10 изображений",
    "first_code": "Первый код",
    "week_active": "Неделя активности",
    "month_active": "Месяц активности",
}
