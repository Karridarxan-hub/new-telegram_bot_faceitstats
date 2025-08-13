# FACEIT Telegram Bot

🎮 Асинхронный телеграм бот для автоматического получения детальной статистики ваших матчей CS2 на платформе FACEIT.

**Технологии:** Python 3.13, aiogram 3.20, aiohttp, pydantic

## Возможности

- 📊 **Детальная статистика** по каждому завершенному матчу
- 🔔 **Автоматические уведомления** о новых играх  
- 👥 **Командная статистика** всех игроков в матче
- 📈 **История матчей** с результатами
- 🏆 **Информация о профиле** FACEIT
- ⚡ **Асинхронная работа** с высокой производительностью

## Установка и настройка

### 1. Требования
- Python 3.13+
- pip (менеджер пакетов Python)

### 2. Клонирование репозитория
```bash
git clone <repository-url>
cd faceit-telegram-bot
```

### 3. Создание виртуального окружения
```bash
python -m venv venv

# Windows
venv\\Scripts\\activate

# Linux/macOS  
source venv/bin/activate
```

### 4. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 5. Настройка переменных окружения
Скопируйте `.env.example` в `.env` и заполните необходимые данные:

```bash
cp .env.example .env
```

Отредактируйте `.env` файл:
```env
# Telegram Bot Token от @BotFather
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here

# FACEIT API Key от developers.faceit.com
FACEIT_API_KEY=your_faceit_api_key_here

# Telegram Chat ID куда отправлять уведомления (необязательно)
TELEGRAM_CHAT_ID=your_chat_id_here

# Интервал проверки новых матчей (в минутах)
CHECK_INTERVAL_MINUTES=10

# Уровень логирования
LOG_LEVEL=INFO
```

### 6. Получение необходимых токенов

#### Telegram Bot Token:
1. Напишите [@BotFather](https://t.me/botfather) в Telegram
2. Отправьте команду `/newbot`
3. Следуйте инструкциям и получите токен

#### FACEIT API Key:
1. Перейдите на [developers.faceit.com](https://developers.faceit.com/)
2. Зарегистрируйтесь и создайте новое приложение
3. Получите API ключ

## Запуск

### Основной запуск:
```bash
python main.py
```

### С отслеживанием логов:
```bash
python main.py | tee bot.log
```

## Команды бота

- `/start` - приветствие и инструкция по использованию
- `/setplayer <nickname>` - привязать FACEIT аккаунт
- `/lastmatch` - показать последний матч с детальной статистикой
- `/matches [количество]` - показать последние N матчей (по умолчанию 5, максимум 20)
- `/profile` - показать информацию о FACEIT профиле
- `/help` - справка по командам

## Структура проекта

```
faceit-telegram-bot/
├── bot/
│   ├── __init__.py
│   ├── bot.py               # Основной класс бота
│   └── handlers.py          # Обработчики команд
├── config/
│   ├── __init__.py
│   └── settings.py          # Настройки и конфигурация
├── faceit/
│   ├── __init__.py
│   ├── api.py              # FACEIT API клиент
│   └── models.py           # Pydantic модели данных
├── utils/
│   ├── __init__.py
│   ├── formatter.py        # Форматирование сообщений
│   ├── monitor.py          # Мониторинг новых матчей
│   └── storage.py          # Локальное хранилище
├── main.py                 # Точка входа приложения
├── requirements.txt        # Python зависимости
├── .env.example           # Пример переменных окружения
└── README.md
```

## Архитектура

### Асинхронная обработка
- Все операции выполняются асинхронно с использованием `asyncio`
- Параллельная обработка HTTP запросов к FACEIT API
- Неблокирующее взаимодействие с Telegram API

### Компоненты системы

**Bot (`bot/`):**
- `FaceitTelegramBot` - основной класс бота
- Обработчики команд с полной поддержкой aiogram 3.20
- Автоматические уведомления пользователей

**FACEIT Integration (`faceit/`):**
- `FaceitAPI` - асинхронный HTTP клиент для FACEIT API
- Pydantic модели для валидации данных
- Обработка ошибок и повторные попытки

**Data Management (`utils/`):**
- `DataStorage` - асинхронное JSON хранилище
- `MessageFormatter` - форматирование для Telegram
- `MatchMonitor` - фоновый мониторинг матчей

### Мониторинг матчей
- Периодическая проверка новых матчей (настраивается в `.env`)
- Автоматические уведомления при завершении матчей
- Отслеживание последнего проверенного матча для каждого пользователя

## Примеры статистики

### Личная статистика в матче:
- **K/D соотношение** с детализацией убийств/смертей
- **ADR** (Average Damage per Round)
- **Процент headshot'ов** и общее количество
- **MVP раунды** и достижения
- **Multi-kill'ы** (triple, quadro, penta kills)

### Командная статистика:
- **Результат матча** (победа/поражение) 
- **Счет раундов** и карта
- **Детальная статистика всех игроков** обеих команд
- **Ссылка на матч** на FACEIT

## Логирование

Бот ведет подробные логи:
- Консольный вывод для мониторинга
- Файл `bot.log` для постоянного хранения
- Настраиваемый уровень логирования через `.env`

## Обработка ошибок

- **Graceful degradation** при недоступности FACEIT API
- **Повторные попытки** для сетевых запросов
- **Валидация данных** с помощью Pydantic
- **Подробное логирование** ошибок

## Производительность

- **Асинхронные HTTP запросы** с aiohttp
- **Пулинг соединений** для оптимизации
- **Batch обработка** пользователей при мониторинге
- **Минимальное потребление памяти**

## Развертывание

### Docker (рекомендуется)
```dockerfile
FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
CMD ["python", "main.py"]
```

### Systemd Service (Linux)
```ini
[Unit]
Description=FACEIT Telegram Bot
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/faceit-telegram-bot
ExecStart=/path/to/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Технические особенности

- **Python 3.13** с использованием новейших возможностей
- **aiogram 3.20** для современной работы с Telegram Bot API
- **aiohttp** для высокопроизводительных HTTP запросов
- **pydantic** для строгой типизации и валидации данных
- **Async/await** паттерн для всех I/O операций

## Мониторинг и отладка

### Проверка статуса:
```python
# В коде бота доступны методы для мониторинга
monitor.status  # Статус мониторинга
await storage.get_all_users()  # Список всех пользователей
```

### Просмотр логов:
```bash
tail -f bot.log  # Мониторинг в реальном времени
```

## Лицензия

MIT License - используйте свободно в личных и коммерческих проектах.

## Поддержка и развитие

- Создавайте Issues для сообщений об ошибках
- Pull Requests приветствуются
- Следите за обновлениями FACEIT и Telegram Bot API

---

**🎮 Приятной игры и точной статистики!**

*Разработано с использованием современных технологий Python для максимальной производительности и надежности.*