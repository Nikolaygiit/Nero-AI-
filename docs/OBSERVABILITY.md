# Observability — Prometheus + Grafana

Метрики позволяют видеть: количество запросов, время ответа, ошибки и расход токенов.

## Метрики

| Метрика | Описание |
|---------|----------|
| `llm_requests_total` | Всего запросов к LLM (по провайдеру и модели) |
| `llm_response_time_seconds` | Время ответа (гистограмма) |
| `llm_errors_total` | Количество ошибок |
| `llm_tokens_total` | Использованные токены |

## Запуск Prometheus

### prometheus.yml

```yaml
scrape_configs:
  - job_name: 'nero-ai'
    static_configs:
      - targets: ['host.docker.internal:9090']
    scrape_interval: 15s
```

### Docker Compose (расширение)

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9091:9090"
    extra_hosts:
      - "host.docker.internal:host-gateway"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    depends_on:
      - prometheus
```

## Grafana Dashboard

1. Добавьте источник данных Prometheus: `http://prometheus:9090`
2. Создайте панели:
   - **requests_per_minute**: `rate(llm_requests_total[1m]) * 60`
   - **average_response_time**: `histogram_quantile(0.95, rate(llm_response_time_seconds_bucket[5m]))`
   - **errors_count**: `increase(llm_errors_total[1h])`
   - **token_usage**: `increase(llm_tokens_total[1h])`

## Конфигурация бота

```env
METRICS_PORT=9090
```

Метрики доступны по адресу: `http://localhost:9090/metrics`.
