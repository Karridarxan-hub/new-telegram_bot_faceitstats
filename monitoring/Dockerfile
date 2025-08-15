# Многоэтапная сборка для оптимизации размера образа
# Этап 1: Сборочный образ с полным Python для установки зависимостей
FROM python:3.11-slim as builder

# Устанавливаем системные зависимости для сборки
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libc6-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Создаем виртуальное окружение
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Устанавливаем зависимости для monitoring службы
COPY requirements-monitoring.txt /tmp/requirements-monitoring.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements-monitoring.txt

# Этап 2: Продакшн образ с минимальными зависимостями
FROM python:3.11-slim as production

# Метаданные для monitoring и observability
LABEL maintainer="FACEIT Telegram Bot Team" \
      service="monitoring" \
      version="1.0.0" \
      description="Monitoring dashboard for FACEIT Telegram Bot services" \
      port="9181"

# Создаем непривилегированного пользователя для безопасности
RUN groupadd -r monitoring && useradd -r -g monitoring -d /app -s /bin/false monitoring

# Устанавливаем только runtime зависимости
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Копируем виртуальное окружение из builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Создаем рабочую директорию
WORKDIR /app

# Копируем код приложения с правильными permissions
COPY --chown=monitoring:monitoring monitoring.py ./
COPY --chown=monitoring:monitoring templates/ ./templates/
COPY --chown=monitoring:monitoring static/ ./static/

# Создаем директории для логов и temp файлов
RUN mkdir -p /app/logs /app/tmp && \
    chown -R monitoring:monitoring /app

# Переключаемся на непривилегированного пользователя
USER monitoring

# Настройки для продакшена
ENV FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    MONITORING_PORT=9181

# Экспонируем порт приложения
EXPOSE 9181

# Health check для Kubernetes/Docker
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:9181/api/health', timeout=5)" || exit 1

# Точка входа с оптимизированными настройками Python
ENTRYPOINT ["python", "-O", "monitoring.py"]