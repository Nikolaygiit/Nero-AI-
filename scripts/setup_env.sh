#!/bin/sh
# Создаёт .env из .env.example, если .env ещё нет. Запуск из корня проекта.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Created .env from .env.example. Edit .env and set ARTEMOX_API_KEY, TELEGRAM_BOT_TOKEN, WEBHOOK_URL."
else
    echo ".env already exists."
fi
