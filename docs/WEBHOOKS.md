# Webhooks — High Load режим

Polling (бот сам спрашивает Telegram «есть новые сообщения?») удобен для разработки, но при 1000+ сообщений в минуту даёт задержки. Webhooks позволяют Telegram самому слать обновления на ваш сервер.

## Запуск всего стека одной командой

В корне проекта уже есть `.env` (скопирован из `.env.example`). Отредактируйте `.env`: подставьте `ARTEMOX_API_KEY`, `TELEGRAM_BOT_TOKEN`, `WEBHOOK_URL` (ваш домен с HTTPS). Затем:

**Windows:**
```bat
scripts\run_full_stack.bat
```

**Linux/macOS:**
```bash
chmod +x scripts/run_full_stack.sh && ./scripts/run_full_stack.sh
```

Поднимаются: **PostgreSQL**, **Redis**, **бот** (с миграциями Alembic при старте), **worker**, **админка**. В контейнерах уже заданы `DATABASE_URL=postgresql://nero:nero@postgres:5432/nero_ai` и `REDIS_URL=redis://redis:6379/0`. Для приёма webhook настройте Nginx по инструкции ниже и укажите в `.env` свой `WEBHOOK_URL`.

## Требования

- **Домен** (или белый IP)
- **SSL-сертификат** (Let's Encrypt или самоподписанный)
- **Nginx** как reverse proxy перед ботом

## Автоматическая настройка (Linux)

Запустите один скрипт — он установит Nginx, Certbot и настроит всё:

```bash
sudo chmod +x scripts/setup_webhooks.sh
sudo ./scripts/setup_webhooks.sh your-domain.com
```

Затем добавьте в `.env` и запустите бота (см. ниже).

## Настройка .env

```env
USE_WEBHOOKS=true
WEBHOOK_URL=https://your-domain.com
WEBHOOK_PORT=8443
```

## Вариант 1: Nginx + Let's Encrypt (рекомендуется)

### 1. Установите Nginx и Certbot

```bash
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx
```

### 2. Получите SSL-сертификат

Замените `your-domain.com` на ваш домен. DNS должен указывать на IP сервера.

```bash
sudo certbot --nginx -d your-domain.com
```

Certbot автоматически настроит Nginx. Если нужен только прокси к боту — добавьте/измените `location /webhook` в конфиге.

### 3. Конфиг Nginx для webhook

Создайте или отредактируйте `/etc/nginx/sites-available/nero-ai`:

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location /webhook {
        proxy_pass http://127.0.0.1:8443;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Включите конфиг и перезапустите Nginx:

```bash
sudo ln -sf /etc/nginx/sites-available/nero-ai /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 4. Откройте порт 443 (если firewall включён)

```bash
sudo ufw allow 443/tcp
sudo ufw reload
```

### 5. Запуск бота

Бот слушает порт 8443. Nginx принимает HTTPS на 443 и проксирует `/webhook` на `localhost:8443`.

```bash
python main.py
```

## Вариант 2: Самоподписанный сертификат (для тестов)

```bash
openssl req -newkey rsa:2048 -sha256 -nodes -keyout private.key -x509 -days 365 -out public.pem -subj "/CN=your-domain.com"
```

В `main.py` при `run_webhook` можно передать `cert` и `key` для самоподписанного сертификата. См. [документацию python-telegram-bot](https://docs.python-telegram-bot.org/en/stable/telegram.ext.application.html#telegram.ext.Application.run_webhook).

## Docker

### Вариант A: Только бот (Nginx на хосте)

```bash
docker compose -f docker-compose.yml up -d
# Бот: порт 8443. На хосте настройте Nginx по инструкции выше.
```

В `.env` контейнера: `USE_WEBHOOKS=true`, `WEBHOOK_URL=https://your-domain.com`, `WEBHOOK_PORT=8443`.

### Вариант B: Полный стек (bot + nginx в Docker)

1. Получите сертификаты на хосте: `sudo certbot certonly --standalone -d your-domain.com`
2. Скопируйте: `sudo cp -rL /etc/letsencrypt ./deploy/certs`
3. В `deploy/nginx-webhook-docker.conf` замените `your-domain.com` на ваш домен
4. Запуск: `DOMAIN=your-domain.com docker compose -f docker-compose.yml -f docker-compose.webhooks.yml up -d`

## Проверка

После запуска бота Telegram сразу начнёт слать обновления на `https://your-domain.com/webhook`. Проверьте логи: `bot_started_webhook`.
