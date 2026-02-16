#!/bin/sh
# Запуск миграций Alembic перед стартом бота при наличии DATABASE_URL
set -e
if [ -n "$DATABASE_URL" ] && [ "$1" = "python" ] && [ "$2" = "main.py" ]; then
    echo "Running Alembic migrations (DATABASE_URL is set)..."
    alembic upgrade head
fi
exec "$@"
