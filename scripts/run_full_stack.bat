@echo off
REM Полный запуск: .env + Docker (postgres, redis, bot, worker, admin). Запуск из корня проекта.
cd /d "%~dp0\.."
if not exist .env (
    call scripts\setup_env.bat
)
echo Starting full stack (postgres, redis, bot, worker, admin)...
docker compose up -d
echo Done. Bot: env from .env + DATABASE_URL=postgres, REDIS_URL=redis. Check: docker compose logs -f bot
