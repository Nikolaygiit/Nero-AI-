# Nero AI Bot

Telegram-бот с поддержкой LLM (Gemini/Artemox API), RAG, генерации изображений, голосового ввода и подписок.

## Требования

- Python 3.10+
- В `.env`: `TELEGRAM_BOT_TOKEN`, `ARTEMOX_API_KEY` (обязательно). Остальные переменные — см. `config.py`.

## Запуск

```bash
pip install -r requirements.txt
python main.py
```

Docker: см. `Dockerfile` и `docs/CICD.md`.

## Структура проекта

Описание архитектуры, цепочки обработки (handler → run_gemini_command / gemini_service, cascade, llm_common, RAG) и зависимостей — в **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

Кратко:

- **Точка входа:** `main.py` — инициализация приложения, обработчики, polling или webhooks.
- **Обработчики:** `handlers/` — чат (`chat.py`), команды (`commands.py`), callbacks, админка, документы, медиа.
- **Сервисы:** `services/` — `gemini.py` (генерация текста/стрим/vision), `llm_cascade.py` (Circuit Breaker + каскад моделей), `llm_common.py` (общие константы и хелперы), `rag.py`, `memory.py`, `speech.py`, `image_gen.py`.
- **Конфиг:** `config.py` (pydantic-settings, валидация при старте).
- **Тесты:** `tests/` — unit и интеграционные; общие моки в `tests/conftest.py` и `tests/mocks.py`.

## Админ-команды

- `/health` — проверка состояния БД и Redis (только для админов из `ADMIN_IDS`).
- `/users`, `/broadcast`, `/logs` — см. `handlers/admin.py`.

## Типизация (mypy)

Опционально: `pip install mypy` и `mypy services/`. В `pyproject.toml` настроены проверки для `services.llm_common`, `services.gemini`, `services.llm_cascade`. Часть предупреждений исправлена (resp/response на None, bytes в логах); остальные (config, database, аннотации) можно чинить по шагам.

## Pre-commit (опционально)

Перед каждым коммитом можно запускать Ruff и pytest. **Нужен Git-репозиторий** (`git init`, если папка ещё не репо):

```bash
pip install pre-commit
pre-commit install
```

При `git commit` автоматически выполняются `ruff check`, `ruff format` и `pytest tests/`.

## Безопасность

Админ-команды защищены списком `ADMIN_IDS`; секреты — только в env. Кратко: [docs/SECURITY.md](docs/SECURITY.md).

## CI/CD

При push/PR в `main`: Ruff (check + format), pytest. При push в `main` — сборка и push Docker-образа в GHCR. Подробнее: [docs/CICD.md](docs/CICD.md).
