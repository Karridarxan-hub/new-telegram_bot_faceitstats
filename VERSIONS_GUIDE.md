# 🚀 FACEIT Telegram Bot - Руководство по версиям

## 📋 Обзор версий

У нас есть **2 основные версии** бота для разных случаев использования:

### 1. 🛠️ Simple Version (`simple_bot.py`)
**Для разработки и простого деплоя**

#### ✅ Возможности:
- Полнофункциональный Telegram бот
- FSM для управления состояниями диалога
- Меню с кнопками и inline keyboard  
- Все основные команды: `/start`, `/profile`, `/link`, `/stats`, `/help`
- Быстрый поиск никнеймов после `/start`
- Callback handlers для всех inline кнопок

#### 🔧 Технические особенности:
- **Хранилище**: JSON файлы (`data.json`)
- **Зависимости**: Минимальные (aiogram, aiohttp, pydantic)
- **Архитектура**: Простая, всё в одном файле
- **Запуск**: `python simple_bot.py`

#### 📦 Когда использовать:
- Разработка и тестирование
- Простой деплой на VPS
- Малые нагрузки (до 100-200 пользователей)
- Когда не нужна сложная архитектура

---

### 2. 🏢 Enterprise Version (`main.py`)
**Для production и высоких нагрузок**

#### ✅ Возможности:
- Все функции простой версии +
- PostgreSQL для данных пользователей
- Redis для кэширования
- RQ очереди для фоновых задач
- Система воркеров для параллельной обработки
- Мониторинг через RQ Dashboard
- Автоматические миграции базы данных
- Расширенная система подписок

#### 🔧 Технические особенности:
- **Хранилище**: PostgreSQL + Redis
- **Архитектура**: Микросервисы, модульная структура
- **Масштабируемость**: Горизонтальное масштабирование воркеров
- **Мониторинг**: Health checks, метрики
- **Зависимости**: Полный стек (PostgreSQL, Redis, RQ)

#### 📦 Когда использовать:
- Production среда
- Высокие нагрузки (1000+ пользователей)
- Когда нужна надёжность и отказоустойчивость
- Планируется активное развитие функционала

---

## 🐳 Docker конфигурации

### Simple Docker Setup
```bash
# Запуск простой версии в Docker (без БД)
docker-compose -f docker-compose.simple.yml up -d
```
- **Сервисы**: Bot + Redis + PostgreSQL (опционально)
- **Команда**: `python simple_bot.py`
- **Назначение**: Контейнеризация простой версии

### Enterprise Docker Setup  
```bash
# Запуск полной архитектуры
docker-compose up -d
```
- **Сервисы**: Bot + 3 воркера + PostgreSQL + Redis + RQ Dashboard
- **Команда**: `python main.py`  
- **Назначение**: Production deployment

---

## 📁 Структура файлов

### Общие файлы (используются обеими версиями):
```
├── faceit/          # FACEIT API клиент
├── utils/           # Утилиты (formatter, storage, etc.)
├── config/          # Настройки
└── requirements.txt # Python зависимости
```

### Только для Enterprise версии:
```
├── bot/             # Модульная архитектура бота
├── database/        # Модели БД и репозитории  
├── queues/          # Система очередей RQ
├── services/        # Бизнес-логика
├── worker.py        # RQ воркеры
└── alembic/         # Миграции БД
```

---

## ⚙️ Настройка и запуск

### Simple Version
```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Настроить .env
cp .env.example .env
# Добавить TELEGRAM_BOT_TOKEN и FACEIT_API_KEY

# 3. Запустить
python simple_bot.py
```

### Enterprise Version  
```bash
# 1. Docker (рекомендуется)
cp .env.example .env.docker
# Настроить все переменные
docker-compose up -d

# 2. Или локально (для разработки)
# Установить PostgreSQL и Redis
# Настроить подключения в .env
python main.py
```

---

## 🔄 Миграция между версиями

### Из Simple → Enterprise:
1. Экспорт данных из `data.json`
2. Запуск миграций PostgreSQL
3. Импорт данных через `migration/migrate_data.py`

### Из Enterprise → Simple:
1. Экспорт пользователей из PostgreSQL  
2. Конвертация в формат JSON
3. Замена файла `data.json`

---

## 🎯 Рекомендации

### Выбор версии:
- **Simple**: Начинающие, тестирование, до 200 пользователей
- **Enterprise**: Опытные разработчики, production, 500+ пользователей

### Развитие:
- Начать с Simple версии
- При росте нагрузки мигрировать на Enterprise
- Новые фичи добавлять в обе версии

### Поддержка:
- Simple версия: минимальная поддержка
- Enterprise версия: активное развитие

---

## 📞 Команды запуска

```bash
# Simple версия
python simple_bot.py

# Enterprise версия (локально)  
python main.py

# Docker simple
docker-compose -f docker-compose.simple.yml up -d

# Docker enterprise
docker-compose up -d
```

---

**Последнее обновление**: Август 2025  
**Версия документа**: 1.0