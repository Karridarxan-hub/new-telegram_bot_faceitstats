# FACEIT Telegram Bot Monitoring Service

Легковесная monitoring служба для мониторинга всех компонентов FACEIT Telegram Bot системы.

## Особенности

- **Легковесный**: Оптимизированный Docker образ на базе Python 3.11-slim
- **Безопасный**: Непривилегированный пользователь, минимальные системные зависимости
- **Производительный**: Multi-stage build, health checks, ограничения ресурсов
- **Мониторинг**: PostgreSQL, Redis, очереди RQ, метрики пользователей

## Быстрый старт

### 1. Сборка и запуск

```bash
# Сборка образа и запуск контейнера
./build-and-run.sh run

# Или только сборка
./build-and-run.sh build

# Только запуск (если образ уже собран)
./build-and-run.sh start
```

### 2. Доступ к dashboard

- **Dashboard**: http://localhost:9181
- **Health check**: http://localhost:9181/api/health
- **Metrics API**: http://localhost:9181/api/metrics

## Конфигурация

### Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `REDIS_URL` | URL для подключения к Redis | `redis://localhost:6379/0` |
| `DATABASE_URL` | URL для подключения к PostgreSQL | - |
| `MONITORING_PORT` | Порт для Flask приложения | `9181` |
| `FLASK_ENV` | Режим Flask | `production` |

### Пример с переменными окружения

```bash
export REDIS_URL="redis://your-redis:6379/0"
export DATABASE_URL="postgresql://user:pass@your-db:5432/faceit_bot"
./build-and-run.sh run
```

## Структура проекта

```
monitoring/
├── Dockerfile              # Оптимизированный Docker образ
├── requirements-monitoring.txt  # Зависимости для monitoring
├── docker-compose.yml      # Для локального тестирования
├── .dockerignore           # Исключения для Docker сборки
├── build-and-run.sh        # Скрипт управления
├── monitoring.py           # Основной код monitoring службы
├── templates/
│   └── dashboard.html      # Web dashboard
└── static/                 # Статические файлы
```

## Docker образ

### Особенности оптимизации

1. **Multi-stage build**: Разделение на builder и production этапы
2. **Slim base image**: Python 3.11-slim вместо полного образа
3. **Непривилегированный пользователь**: Безопасность в production
4. **Minimal dependencies**: Только необходимые runtime библиотеки
5. **Health checks**: Автоматическая проверка состояния службы

### Размер образа

- **Базовый Python 3.11**: ~950MB
- **Наш оптимизированный**: ~150-200MB
- **Экономия**: ~75-80%

## Команды управления

```bash
# Сборка образа
./build-and-run.sh build

# Запуск контейнера
./build-and-run.sh run

# Остановка
./build-and-run.sh stop

# Просмотр логов
./build-and-run.sh logs

# Проверка статуса
./build-and-run.sh status

# Очистка ресурсов
./build-and-run.sh clean

# Перезапуск
./build-and-run.sh restart
```

## Production deployment

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: faceit-monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: faceit-monitoring
  template:
    metadata:
      labels:
        app: faceit-monitoring
    spec:
      containers:
      - name: monitoring
        image: faceit-monitoring:latest
        ports:
        - containerPort: 9181
        env:
        - name: REDIS_URL
          value: "redis://redis-service:6379/0"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: database-url
        resources:
          limits:
            memory: "256Mi"
            cpu: "500m"
          requests:
            memory: "128Mi"
            cpu: "250m"
        livenessProbe:
          httpGet:
            path: /api/health
            port: 9181
          initialDelaySeconds: 30
          periodSeconds: 30
```

### Docker Swarm

```yaml
version: '3.8'
services:
  monitoring:
    image: faceit-monitoring:latest
    ports:
      - "9181:9181"
    environment:
      - REDIS_URL=redis://redis:6379/0
      - DATABASE_URL_FILE=/run/secrets/db_url
    secrets:
      - db_url
    deploy:
      replicas: 1
      resources:
        limits:
          memory: 256M
          cpus: '0.5'
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
```

## Мониторинг метрик

### Доступные эндпоинты

- `GET /api/metrics` - Полная статистика системы
- `GET /api/health` - Health check
- `GET /api/errors` - Последние ошибки

### Интеграция с Prometheus

Monitoring служба готова к интеграции с Prometheus через custom metrics endpoint.

## Безопасность

1. **Непривилегированный пользователь**: Контейнер не запускается от root
2. **Minimal attack surface**: Только необходимые пакеты
3. **Health checks**: Автоматическое определение проблем
4. **Resource limits**: Защита от DoS атак

## Troubleshooting

### Проблемы с подключением к Redis

```bash
# Проверка доступности Redis
docker exec faceit-monitoring python -c "import redis; r=redis.from_url('redis://redis:6379'); print(r.ping())"
```

### Проблемы с подключением к PostgreSQL

```bash
# Проверка подключения к базе
docker exec faceit-monitoring python -c "import asyncpg; print('OK')"
```

### Просмотр детальных логов

```bash
# Логи с timestamp
docker logs -t faceit-monitoring

# Логи в реальном времени
./build-and-run.sh logs
```

## Поддержка

Для вопросов и проблем создавайте issue в репозитории проекта.