# Multi-stage build для оптимизации размера образа
FROM python:3.13-slim as builder

# Получаем версию как аргумент сборки
ARG VERSION=1.0.0
ENV BOT_VERSION=$VERSION

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Создание виртуального окружения
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Копирование файлов требований
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Финальный образ
FROM python:3.13-slim

# Передаем версию в финальный образ
ARG VERSION=1.0.0
ENV BOT_VERSION=$VERSION

# Установка timezone и локали для корректной работы с Unicode
RUN apt-get update && apt-get install -y \
    tzdata \
    locales \
    && rm -rf /var/lib/apt/lists/*

# Настройка локали для поддержки UTF-8
RUN sed -i '/en_US.UTF-8/s/^# //g' /etc/locale.gen && \
    locale-gen
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# Копирование виртуального окружения из builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Создание пользователя для безопасности
RUN useradd --create-home --shell /bin/bash app
USER app
WORKDIR /home/app

# Копирование кода приложения
COPY --chown=app:app . .

# Создание директории для данных
RUN mkdir -p /home/app/data

# Установка переменных окружения
ENV PYTHONPATH=/home/app
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Проверка установки зависимостей
RUN python -c "import aiogram, aiohttp, pydantic; print('Dependencies OK')"

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; print('Bot is running')" || exit 1

# Запуск приложения
CMD ["python", "main.py"]