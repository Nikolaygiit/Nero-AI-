# Полный запуск (всё настроено)

## Что уже сделано

- **`.env`** создан из `.env.example` (webhooks, PostgreSQL, Redis, лимит LLM).
- **Docker Compose** поднимает: PostgreSQL, Redis, бот (с авто-миграциями), worker, админка.
- **Пароль PostgreSQL в контейнерах:** `nero` / `nero`, база `nero_ai` (логин в `.env` для локального запуска можно не менять — в Docker подставляется сам).

## Что сделать вам

1. **Открыть `.env`** и подставить:
   - `ARTEMOX_API_KEY` — ключ с https://artemox.com/ui  
   - `TELEGRAM_BOT_TOKEN` — от @BotFather  
   - `WEBHOOK_URL` — ваш домен с HTTPS (например `https://your-domain.com`)

2. **Запустить стек:**

   **Windows:**
   ```bat
   scripts\run_full_stack.bat
   ```

   **Linux/macOS:**
   ```bash
   chmod +x scripts/run_full_stack.sh && ./scripts/run_full_stack.sh
   ```

3. **Для приёма webhook** (обязательно при 80k пользователей): настроить Nginx + SSL по [WEBHOOKS.md](WEBHOOKS.md). После этого Telegram будет слать обновления на `https://ваш-домен.com/webhook`.

## Проверка

- Логи бота: `docker compose logs -f bot`  
- Админка: http://localhost:8501  
- Миграции БД выполняются при старте контейнера бота, если задан `DATABASE_URL`.

## Проверка Docker-образа (один раз)

Убедиться, что образ собирается и бот стартует с текущим кодом:

```bash
docker build -t nero-ai-bot .
docker run --rm -e TELEGRAM_BOT_TOKEN=test -e ARTEMOX_API_KEY=test nero-ai-bot python -c "import main; print('OK')"
```

Или с `.env` и кратким запуском (остановить через несколько секунд):

```bash
docker build -t nero-ai-bot .
docker run --rm --env-file .env nero-ai-bot
```
