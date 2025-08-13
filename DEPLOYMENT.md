# 🚀 Пошаговый план запуска FACEIT Telegram Bot в продакшн

## 📋 Чек-лист подготовки к запуску

### ✅ Получение необходимых токенов

#### 1. Создание Telegram бота
1. Откройте Telegram и найдите [@BotFather](https://t.me/botfather)
2. Отправьте команду `/newbot`
3. Введите имя вашего бота (например: "FACEIT Stats Bot")
4. Введите username бота (например: "faceit_stats_bot")
5. **Сохраните полученный токен** - он понадобится для `.env` файла
6. Настройте бота:
   - `/setdescription` - описание бота
   - `/setcommands` - список команд:
     ```
     start - Запуск бота и инструкция
     setplayer - Привязать FACEIT аккаунт
     lastmatch - Последний матч с детальной статистикой
     matches - Последние N матчей (по умолчанию 5)
     profile - Информация о FACEIT профиле
     help - Справка по командам
     ```

#### 2. Получение FACEIT API Key
1. Перейдите на [developers.faceit.com](https://developers.faceit.com/)
2. Зарегистрируйтесь или войдите в аккаунт
3. Создайте новое приложение:
   - **Name**: FACEIT Telegram Bot
   - **Description**: Telegram bot for CS2 match statistics
   - **Website**: (можете оставить пустым)
4. **Сохраните API Key** из раздела "API Keys"

#### 3. Получение Telegram Chat ID (опционально)
Если хотите получать уведомления в определенный чат:
1. Добавьте бота [@userinfobot](https://t.me/userinfobot) в Telegram
2. Отправьте ему любое сообщение
3. Бот пришлет ваш Chat ID
4. Или для группового чата: добавьте бота в группу и используйте Chat ID группы

### ✅ Настройка окружения

#### 1. Подготовка сервера (Linux/Ubuntu)
```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python 3.13
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.13 python3.13-venv python3.13-dev -y

# Установка Git
sudo apt install git -y

# Создание пользователя для бота (рекомендуется)
sudo useradd -m -s /bin/bash faceitbot
sudo usermod -aG sudo faceitbot
```

#### 2. Клонирование и настройка проекта
```bash
# Переключение на пользователя бота
sudo su - faceitbot

# Клонирование репозитория
git clone <your-repository-url> faceit-telegram-bot
cd faceit-telegram-bot

# Создание виртуального окружения
python3.13 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

#### 3. Создание .env файла
```bash
# Копирование примера
cp .env.example .env

# Редактирование конфигурации
nano .env
```

**Заполните .env файл вашими данными:**
```env
# Токен от @BotFather
TELEGRAM_BOT_TOKEN=1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA

# API ключ от developers.faceit.com
FACEIT_API_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Chat ID для уведомлений (необязательно)
TELEGRAM_CHAT_ID=123456789

# Интервал проверки в минутах (рекомендуется 5-15)
CHECK_INTERVAL_MINUTES=10

# Уровень логирования
LOG_LEVEL=INFO
```

### ✅ Тестирование перед запуском

#### 1. Проверка конфигурации
```bash
# Активация окружения
source venv/bin/activate

# Тестовый запуск
python main.py
```

**Ожидаемый вывод:**
```
✅ Configuration validated successfully
🚀 Starting FACEIT Stats Bot...
INFO - Bot started successfully
INFO - Match monitor started
```

#### 2. Тестирование основных команд
1. Найдите бота в Telegram по username
2. Отправьте `/start` - должно прийти приветственное сообщение
3. Отправьте `/setplayer your_faceit_nickname`
4. Отправьте `/profile` - должна прийти информация о профиле
5. Отправьте `/lastmatch` - должна прийти статистика последнего матча

### ✅ Настройка автозапуска (Systemd Service)

#### 1. Создание systemd сервиса
```bash
sudo nano /etc/systemd/system/faceitbot.service
```

**Содержимое файла:**
```ini
[Unit]
Description=FACEIT Telegram Bot
After=network.target
Wants=network.target

[Service]
Type=simple
User=faceitbot
Group=faceitbot
WorkingDirectory=/home/faceitbot/faceit-telegram-bot
Environment=PATH=/home/faceitbot/faceit-telegram-bot/venv/bin
ExecStart=/home/faceitbot/faceit-telegram-bot/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=faceitbot

# Безопасность
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/home/faceitbot/faceit-telegram-bot
ProtectHome=yes

[Install]
WantedBy=multi-user.target
```

#### 2. Запуск и включение сервиса
```bash
# Перезагрузка systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable faceitbot

# Запуск сервиса
sudo systemctl start faceitbot

# Проверка статуса
sudo systemctl status faceitbot
```

### ✅ Мониторинг и логи

#### 1. Просмотр логов
```bash
# Логи systemd
sudo journalctl -u faceitbot -f

# Файл логов приложения
tail -f /home/faceitbot/faceit-telegram-bot/bot.log

# Логи за последний час
sudo journalctl -u faceitbot --since "1 hour ago"
```

#### 2. Управление сервисом
```bash
# Остановка
sudo systemctl stop faceitbot

# Перезапуск
sudo systemctl restart faceitbot

# Статус
sudo systemctl status faceitbot

# Отключение автозапуска
sudo systemctl disable faceitbot
```

### ✅ Backup и обновления

#### 1. Резервное копирование
```bash
# Создание backup скрипта
nano ~/backup_bot.sh
```

**Содержимое скрипта:**
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/home/faceitbot/backups"
BOT_DIR="/home/faceitbot/faceit-telegram-bot"

mkdir -p $BACKUP_DIR
tar -czf "$BACKUP_DIR/faceitbot_backup_$DATE.tar.gz" \
  --exclude="venv" \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  -C /home/faceitbot faceit-telegram-bot

echo "Backup created: faceitbot_backup_$DATE.tar.gz"
```

```bash
chmod +x ~/backup_bot.sh
```

#### 2. Обновление бота
```bash
# Остановка сервиса
sudo systemctl stop faceitbot

# Резервное копирование
~/backup_bot.sh

# Обновление кода
cd /home/faceitbot/faceit-telegram-bot
git pull origin main

# Обновление зависимостей
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Запуск сервиса
sudo systemctl start faceitbot

# Проверка статуса
sudo systemctl status faceitbot
```

### ✅ Безопасность

#### 1. Файрвол
```bash
# Установка ufw
sudo apt install ufw -y

# Базовые правила
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw enable
```

#### 2. Защита .env файла
```bash
# Ограничение прав доступа
chmod 600 .env
chown faceitbot:faceitbot .env
```

### ✅ Мониторинг производительности

#### 1. Системные ресурсы
```bash
# Использование памяти и CPU
ps aux | grep python
htop

# Использование диска
df -h
du -sh /home/faceitbot/faceit-telegram-bot/
```

#### 2. Статистика бота
```bash
# Количество пользователей
grep -c "setplayer" bot.log

# Активность за день
grep "$(date +%Y-%m-%d)" bot.log | wc -l

# Ошибки
grep -i error bot.log | tail -10
```

### 🆘 Устранение проблем

#### Типичные проблемы:

1. **Бот не отвечает на команды**
   - Проверьте токен в .env файле
   - Убедитесь, что сервис запущен: `sudo systemctl status faceitbot`

2. **Ошибки FACEIT API**
   - Проверьте API ключ в .env файле
   - Убедитесь, что лимиты API не превышены

3. **Высокое потребление ресурсов**
   - Увеличьте `CHECK_INTERVAL_MINUTES` в .env
   - Проверьте логи на наличие повторяющихся ошибок

4. **Бот перестал мониторить матчи**
   - Перезапустите сервис: `sudo systemctl restart faceitbot`
   - Проверьте интернет соединение
   - Проверьте статус FACEIT API: [status.faceit.com](https://status.faceit.com)

### 📊 Рекомендации по производительности

1. **Оптимальные настройки:**
   - `CHECK_INTERVAL_MINUTES=10` для обычного использования
   - `CHECK_INTERVAL_MINUTES=5` для активных игроков
   - `LOG_LEVEL=INFO` для продакшена

2. **Мониторинг:**
   - Настройте rotation логов: `logrotate`
   - Мониторьте использование диска
   - Отслеживайте время отклика API

3. **Масштабирование:**
   - При >100 пользователей рассмотрите использование Redis для хранения
   - При >500 пользователей рассмотрите несколько инстансов бота

---

## 🎯 Финальный чек-лист запуска

- [ ] Получены все токены (Telegram Bot, FACEIT API)
- [ ] Создан и настроен .env файл
- [ ] Проект склонирован и зависимости установлены
- [ ] Выполнено тестирование основных функций
- [ ] Настроен systemd сервис
- [ ] Проверена работа автозапуска
- [ ] Настроены логи и мониторинг
- [ ] Созданы backup процедуры
- [ ] Документированы процедуры обновления

**🚀 Ваш FACEIT Telegram Bot готов к работе в продакшене!**