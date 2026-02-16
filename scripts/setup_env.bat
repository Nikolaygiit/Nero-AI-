@echo off
REM Создаёт .env из .env.example, если .env ещё нет. Запуск из корня проекта.
cd /d "%~dp0\.."
if not exist .env (
    copy .env.example .env
    echo Created .env from .env.example. Edit .env and set ARTEMOX_API_KEY, TELEGRAM_BOT_TOKEN, WEBHOOK_URL.
) else (
    echo .env already exists.
)
