#!/bin/bash
# Автоматическая настройка Webhooks: Nginx + Let's Encrypt
# Использование: sudo ./scripts/setup_webhooks.sh your-domain.com
# Требуется: root, домен должен указывать на IP сервера

set -e

DOMAIN="${1:-}"
if [ -z "$DOMAIN" ]; then
    echo "Использование: sudo $0 your-domain.com"
    exit 1
fi

BOT_PORT=8443
NGINX_CONF="/etc/nginx/sites-available/nero-ai"

echo "=== Установка Nginx и Certbot ==="
apt-get update -qq
apt-get install -y nginx certbot python3-certbot-nginx

echo "=== Получение SSL-сертификата ==="
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email || true

echo "=== Создание конфига Nginx ==="
cat > "$NGINX_CONF" << EOF
server {
    listen 443 ssl;
    server_name $DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;

    location /webhook {
        proxy_pass http://127.0.0.1:$BOT_PORT;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

rm -f /etc/nginx/sites-enabled/default
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

echo "=== Открытие порта 443 ==="
ufw allow 443/tcp 2>/dev/null && ufw reload 2>/dev/null || true

echo "=== Готово ==="
echo "Добавьте в .env:"
echo "  USE_WEBHOOKS=true"
echo "  WEBHOOK_URL=https://$DOMAIN"
echo "  WEBHOOK_PORT=$BOT_PORT"
echo ""
echo "Запустите бота: python main.py"
