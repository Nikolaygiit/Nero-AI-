# Архитектура проекта Nero-AI Bot

## Точка входа

- **`main.py`** — запуск бота: загрузка config, инициализация БД (`db.init`), регистрация обработчиков, запуск polling или webhook. Конфигурация валидируется при импорте (pydantic-settings).

## Цепочка обработки сообщений

### Текстовые сообщения (не команды)

1. **`handlers.chat.handle_message`**  
   Проверки: бан, rate limit, лимит запросов в день.  
   Затем:
   - **Запрос картинки** (по ключевым словам) → Taskiq/очередь или синхронно `services.image_gen.generate_with_queue`.
   - **Вопрос по последнему фото** (есть `last_image_base64` в `context.user_data`) → `gemini_service.generate_with_image_context` (мультимодальный ответ).
   - **Обычный текст** → RAG-контекст `get_rag_context`, затем потоковая генерация.

2. **Потоковая генерация**  
   `gemini_service.generate_content_stream` (с RAG и историей). При ошибке стрима — fallback на `generate_and_reply_text`, внутри которого вызывается `generate_content` (не стрим).

3. **Ответ пользователю**  
   Обновление сообщения по мере прихода токенов, затем финальный ответ с кнопками «Перегенерировать» / «Перефразировать».

### Команды с LLM (translate, summarize, explain, quiz, …)

- **`handlers.commands.run_gemini_command`** — общий поток: rate limit → typing → `gemini_service.generate_content(prompt, user_id, use_context=False)` → ответ по шаблону → `db.update_stats`.
- Команды передают в хелпер `prompt`, `success_formatter` и имя команды.

### Callbacks (кнопки)

- **`handlers.callbacks.button_callback`**  
  Обработка `callback_data`: меню моделей, retry, rephrase, избранное и т.д.
- **Retry** (`retry_{user_id}_{request_id}`): берёт промпт из `context.user_data["prompts"][request_id]`, вызывает `generate_and_reply_text` (из `handlers.chat`) и отправляет новый ответ с кнопками.
- **Rephrase** (`rephrase_{user_id}`): запрос к `gemini_service.generate_content` с просьбой перефразировать последний запрос, затем генерация ответа по новой формулировке.

## Сервисы и общий слой LLM

### services.gemini (GeminiService)

- **`generate_content`** — подготовка контекста `_prepare_messages_context`, затем вызов cascade (`services.llm_cascade.chat_completion`), при ошибке — legacy fallback по моделям.
- **`generate_content_stream`** — те же сообщения, стрим по моделям, при неудаче — fallback на `generate_content`.
- **`generate_with_image_context`** / **`analyze_image`** — vision: сборка сообщений с изображением, цикл по vision-моделям `_execute_vision_request`.

### services.llm_cascade

- Каскад провайдеров: Artemox (Gemini) → DeepSeek → OpenAI.
- Circuit Breaker по моделям: после N ошибок модель временно отключается.
- **`chat_completion(messages, max_tokens, stream, model_hint)`** — возвращает `(text, model_used, tokens)`.

### services.llm_common

- Общие константы и типы для LLM: **`CHAT_URL_PATH`**, **`DEFAULT_REQUEST_TIMEOUT`**, **`MODEL_TIMEOUT_SEC`**, **`build_chat_url`**, **`build_headers`**, **`ChatMessage`** (TypedDict). Используются в `gemini`, `llm_cascade`, `rag`, `speech`.

### RAG и память

- **services.rag** — PDF → чанки → эмбеддинги (Artemox `/embeddings`, заголовки через `build_headers`) → ChromaDB. **`get_rag_context(user_id, query)`** возвращает текст для вставки в системный промпт.
- **services.memory** — извлечение фактов из сообщений (Gemini API), сохранение в БД, **`get_relevant_facts(user_id)`** для вставки в системный промпт.

## База данных

- **database.db** — асинхронный слой (SQLAlchemy, aiosqlite). Методы: `get_user`, `get_user_messages`, `add_message`, `update_stats`, `is_banned`, `increment_daily_usage` и др.
- **database.models** — User, Message, Stats, Favorite, Subscription, UsageDaily, UserFact, Achievement.

## Middlewares и утилиты

- **middlewares.rate_limit** — лимит запросов в минуту на пользователя.
- **middlewares.usage_limit** — лимит бесплатных запросов в день.
- **utils.i18n** — переводы строк (t).
- **utils.error_middleware** — глобальный обработчик ошибок (лог + сообщение пользователю).

## Структура каталогов (основное)

```
main.py              # Точка входа
config.py            # Конфигурация (pydantic-settings)
handlers/            # Обработчики команд и сообщений (chat, commands, callbacks, media, …)
services/            # gemini, llm_cascade, llm_common, rag, memory, image_gen, speech
database/            # db, models; миграции alembic
middlewares/         # rate_limit, usage_limit, ban_check
utils/               # logging_config, i18n, analytics, metrics, error_middleware, text_tools
tasks/               # Taskiq + Redis (очередь генерации изображений)
tests/               # conftest.py, mocks.py, test_*.py
docs/                # ARCHITECTURE.md, WEBHOOKS.md, CICD.md, OBSERVABILITY.md
```

## Зависимости между модулями

- **main** → config, database.db, handlers.*, utils.error_middleware, utils.logging_config
- **handlers.chat** → database.db, services.gemini, services.rag, services.memory, middlewares, utils
- **handlers.commands** → run_gemini_command → services.gemini.generate_content, database.db
- **services.gemini** → config, database.db, services.llm_common, services.memory (get_relevant_facts), services.llm_cascade (chat_completion)
- **services.llm_cascade** → config, services.llm_common (build_chat_url, build_headers, ChatMessage, MODEL_TIMEOUT_SEC)
