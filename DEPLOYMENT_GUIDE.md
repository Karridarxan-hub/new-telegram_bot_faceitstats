# 🚀 FACEIT Telegram Bot - Production Deployment Guide

## 📋 Пошаговая инструкция для развертывания на VPS

### Требования к VPS
- **Минимум:** 1GB RAM, 1 vCPU, 10GB SSD
- **Рекомендуется:** 2GB RAM, 2 vCPU, 20GB SSD
- **ОС:** Ubuntu 20.04/22.04 или Debian 11/12

---

## 🔧 ШАГ 1: Регистрация внешних сервисов (15 минут)

### PostgreSQL база данных

#### Вариант A: ElephantSQL (Рекомендуется - БЕСПЛАТНО)
1. Зайдите на https://elephantsql.com
2. Создайте аккаунт через GitHub/Google
3. Create New Instance → Tiny Turtle (Free)
4. Скопируйте PostgreSQL URL

#### Вариант B: Supabase (БЕСПЛАТНО)
1. Зайдите на https://supabase.com
2. Create New Project
3. Settings → Database → Connection String
4. Скопируйте URL

### Redis кеширование

#### Вариант A: Upstash (Рекомендуется - БЕСПЛАТНО)
1. Зайдите на https://upstash.com
2. Create Database → Regional → Free Plan
3. Скопируйте Redis URL

#### Вариант B: Redis Cloud (БЕСПЛАТНО)
1. Зайдите на https://redis.com/try-free/
2. Create Subscription → 30MB Free
3. Скопируйте Connection String

---

## 🖥️ ШАГ 2: Настройка VPS (20 минут)

### Подключение к VPS
```bash
ssh root@your-vps-ip
```

### Быстрая установка (скопируйте и запустите)
```bash
# Скачайте deployment скрипт
wget https://raw.githubusercontent.com/your-repo/faceit-telegram-bot/master/deploy.sh
chmod +x deploy.sh
./deploy.sh
```

### Ручная установка (если нужен контроль)

#### 1. Обновите систему
```bash
apt update && apt upgrade -y
```

#### 2. Установите Docker
```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER
```

#### 3. Установите Docker Compose
```bash
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
```

#### 4. Клонируйте репозиторий
```bash
cd ~
git clone https://github.com/your-repo/faceit-telegram-bot.git
cd faceit-telegram-bot
```

---

## ⚙️ ШАГ 3: Конфигурация (10 минут)

### Создайте .env файл
```bash
cp .env.production .env
nano .env
```

### Заполните ваши данные:
```env
# Telegram (у вас уже есть)
TELEGRAM_BOT_TOKEN=8200317917:AAE3wSxtG6N7wKeLJezgNaQsCd5uHMcXjVk

# FACEIT (у вас уже есть)
FACEIT_API_KEY=41f48f43-609c-4639-b821-360b039f18b4

# PostgreSQL (вставьте URL из ElephantSQL)
DATABASE_URL=postgresql://username:password@server.elephantsql.com/database

# Redis (вставьте URL из Upstash)
REDIS_URL=redis://default:password@endpoint.upstash.io:6379
```

---

## 🚀 ШАГ 4: Запуск бота (5 минут)

### Для Simple версии (рекомендуется для начала):
```bash
docker-compose -f docker-compose.production.yml up -d
```

### Проверка статуса:
```bash
# Посмотреть статус
docker-compose -f docker-compose.production.yml ps

# Посмотреть логи
docker-compose -f docker-compose.production.yml logs -f faceit-bot

# Перезапустить
docker-compose -f docker-compose.production.yml restart
```

---

## 🔄 ШАГ 5: Автозапуск при перезагрузке VPS

### Создайте systemd сервис:
```bash
sudo nano /etc/systemd/system/faceit-bot.service
```

### Вставьте:
```ini
[Unit]
Description=FACEIT Telegram Bot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/root/faceit-telegram-bot
ExecStart=/usr/local/bin/docker-compose -f docker-compose.production.yml up -d
ExecStop=/usr/local/bin/docker-compose -f docker-compose.production.yml down
TimeoutStartSec=0
User=root

[Install]
WantedBy=multi-user.target
```

### Активируйте:
```bash
sudo systemctl daemon-reload
sudo systemctl enable faceit-bot
sudo systemctl start faceit-bot
```

---

## 📊 ШАГ 6: Мониторинг

### Базовые команды:
```bash
# Статус бота
docker-compose -f docker-compose.production.yml ps

# Логи в реальном времени
docker-compose -f docker-compose.production.yml logs -f

# Использование ресурсов
docker stats

# Системные ресурсы
htop
```

### Настройка алертов (опционально):
```bash
# Установите monitoring
apt install -y netdata
```

Откройте http://your-vps-ip:19999 для мониторинга

---

## 🆘 Решение проблем

### Бот не запускается:
```bash
# Проверьте логи
docker-compose -f docker-compose.production.yml logs faceit-bot

# Проверьте .env файл
cat .env | grep TOKEN
```

### Нет соединения с БД:
```bash
# Проверьте DATABASE_URL
echo $DATABASE_URL

# Тестируйте подключение
apt install postgresql-client
psql YOUR_DATABASE_URL
```

### Высокая нагрузка:
```bash
# Перезапустите бота
docker-compose -f docker-compose.production.yml restart

# Очистите логи
docker system prune -a
```

---

## 📈 Масштабирование

### Когда переходить на Enterprise версию:
- Более 200 активных пользователей
- Нужны фоновые задачи
- Требуется высокая доступность

### Миграция на Enterprise:
1. Измените command в docker-compose.yml:
   ```yaml
   command: python main.py  # вместо simple_bot.py
   ```

2. Добавьте воркеры:
   ```yaml
   worker:
     image: faceit-bot:production
     command: python worker.py
   ```

3. Перезапустите:
   ```bash
   docker-compose down
   docker-compose up -d
   ```

---

## 🔒 Безопасность

### Обязательные шаги:
```bash
# Настройте firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# Создайте non-root пользователя
adduser botuser
usermod -aG docker botuser
su - botuser

# Защитите .env файл
chmod 600 .env
```

### Резервное копирование:
```bash
# Ежедневный backup данных
crontab -e
0 2 * * * tar -czf /backup/bot-$(date +\%Y\%m\%d).tar.gz /root/faceit-telegram-bot/data
```

---

## ✅ Чек-лист после развертывания

- [ ] Бот отвечает в Telegram
- [ ] Команда `/start` работает
- [ ] Команда `/profile Geun-Hee` возвращает данные
- [ ] Логи не показывают ошибок
- [ ] Автозапуск настроен
- [ ] Firewall включен
- [ ] Backup настроен

---

## 📞 Поддержка

### Полезные ресурсы:
- Документация: `/TECHNICAL_ARCHITECTURE.md`
- Логи: `docker-compose logs -f`
- Статус: `docker-compose ps`

### Команды для отладки:
```bash
# Полный рестарт
docker-compose down && docker-compose up -d

# Обновление кода
git pull && docker-compose restart

# Очистка системы
docker system prune -a
```

---

## 🎉 Готово!

Ваш бот теперь работает в production! 

Проверьте его в Telegram: **@faceitstatsme_bot**

Следующие шаги:
1. Мониторьте логи первые 24 часа
2. Настройте оповещения о падениях
3. Планируйте масштабирование при росте