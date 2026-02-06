#!/bin/sh
# Запуск миграций Alembic перед стартом бота (если первый аргумент — main.py или python main.py)
set -e
if [ "$1" = "python" ] && [ "$2" = "main.py" ]; then
    echo "Running Alembic migrations..."
    alembic upgrade head
fi
exec "$@"
