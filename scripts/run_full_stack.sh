#!/bin/sh
# Полный запуск: .env + Docker (postgres, redis, bot, worker, admin). Запуск из корня проекта.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [ ! -f .env ]; then
    sh scripts/setup_env.sh
fi
echo "Starting full stack (postgres, redis, bot, worker, admin)..."
docker compose up -d
echo "Done. Bot uses .env + DATABASE_URL=postgres, REDIS_URL=redis. Check: docker compose logs -f bot"
