# CI/CD и деплой на сервер

## Что делает GitHub Actions

При **push** или **pull request** в ветку `main`:

1. **Lint (Ruff)** — проверка кода: `ruff check .` и `ruff format --check .`.
2. **Tests (pytest)** — запуск тестов: `pytest tests/ -v` (переменные `ARTEMOX_API_KEY`, `TELEGRAM_BOT_TOKEN` заданы в env для тестов).
3. **Build & Push** (только при push в `main`) — сборка Docker-образа и публикация в **GitHub Container Registry** (ghcr.io).

Образ доступен по адресу:
```
ghcr.io/<ВАШ_ORG_ИЛИ_USER>/<ИМЯ_РЕПО>:latest
ghcr.io/<ВАШ_ORG_ИЛИ_USER>/<ИМЯ_РЕПО>:<sha>
```

Чтобы образ был доступен для pull без логина (например, с сервера), сделайте пакет **публичным**:  
GitHub → репозиторий → **Packages** (справа) → выберите образ → **Package settings** → **Change visibility** → **Public**.

---

## Вариант 1: Watchtower (автообновление контейнеров)

На сервере используйте `docker-compose` с образом из Registry и контейнером Watchtower — он периодически подтягивает новый образ и перезапускает сервисы.

1. Создайте на сервере `docker-compose.prod.yml` (или скопируйте из репозитория).
2. Создайте `.env` с переменными (токен бота, API-ключи и т.д.).
3. Запуск:

```bash
docker compose -f docker-compose.prod.yml up -d
```

Watchtower по умолчанию проверяет обновления каждые 5 минут. Интервал можно изменить переменной `WATCHTOWER_POLL_INTERVAL`.

---

## Вариант 2: Скрипт (pull и перезапуск по расписанию или вручную)

Создайте на сервере скрипт `update_bot.sh`:

```bash
#!/bin/bash
set -e
cd /path/to/your/app  # или каталог с docker-compose
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

Сделайте исполняемым: `chmod +x update_bot.sh`.

Запуск вручную:
```bash
./update_bot.sh
```

Или добавьте в cron (например, каждые 15 минут):
```bash
*/15 * * * * /path/to/your/app/update_bot.sh >> /var/log/nero-update.log 2>&1
```

---

## Первый запуск на сервере (приватный образ)

Если образ **приватный**, на сервере нужно один раз залогиниться в GHCR:

1. Создайте **Personal Access Token** (GitHub → Settings → Developer settings → Personal access tokens) с правом `read:packages`.
2. На сервере:
   ```bash
   echo "YOUR_GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
   ```
3. Дальше `docker compose pull` и `up -d` будут работать без SSH и ручного `git pull`.
