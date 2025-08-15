# 🚀 Автоматический деплой FACEIT Telegram Bot на VPS

## 📋 Что готово:

✅ **GitHub репозиторий:** https://github.com/Karridarxan-hub/new-telegram_bot_faceitstats.git  
✅ **Облачные сервисы:** Upstash Redis + Supabase PostgreSQL  
✅ **Docker контейнеризация:** Готова для продакшена  
✅ **Автоматический деплой скрипт:** Один клик для запуска  

## 🛠 Как задеплоить:

### 1. **Подготовка (уже сделано):**
- ✅ SSH ключ создан: `vps-key.pem`
- ✅ Продакшн конфиг: `.env.production`
- ✅ Деплой скрипт: `deploy-to-vps.sh`

### 2. **Запуск деплоя:**

#### **На Windows (Git Bash):**
```bash
# Откройте Git Bash в папке проекта и выполните:
chmod +x deploy-to-vps.sh
./deploy-to-vps.sh
```

#### **На Linux/macOS:**
```bash
chmod +x deploy-to-vps.sh
./deploy-to-vps.sh
```

### 3. **Что делает скрипт автоматически:**
1. 🔐 Подключается к VPS через SSH ключ
2. 🐳 Устанавливает Docker и Docker Compose
3. 📂 Клонирует проект с GitHub
4. ⚙️ Копирует продакшн настройки
5. 🏗️ Собирает Docker образы
6. 🚀 Запускает все сервисы
7. ✅ Проверяет статус деплоя

## 📊 После деплоя:

### **Проверить статус:**
```bash
ssh -i vps-key.pem root@185.224.132.36 'cd faceit-telegram-bot && docker-compose ps'
```

### **Посмотреть логи:**
```bash
ssh -i vps-key.pem root@185.224.132.36 'cd faceit-telegram-bot && docker-compose logs -f faceit-bot'
```

### **Перезапустить бота:**
```bash
ssh -i vps-key.pem root@185.224.132.36 'cd faceit-telegram-bot && docker-compose restart faceit-bot'
```

### **Мониторинг очередей:**
Откройте в браузере: http://185.224.132.36:9181

## 🔄 Обновление бота:

Когда нужно обновить код:
```bash
# 1. Закоммитьте изменения в Git
git add .
git commit -m "Обновил статистику"
git push origin main

# 2. Запустите деплой
./deploy-to-vps.sh
```

## 🏗️ Архитектура на VPS:

```
VPS (185.224.132.36):
├── faceit-bot (основной бот)
├── worker-priority (важные задачи)
├── worker-default (обычные задачи)  
├── worker-bulk (массовые задачи)
└── rq-dashboard (мониторинг очередей)
         ↓
☁️ Облачные сервисы:
├── Upstash Redis (кеш + очереди)
└── Supabase PostgreSQL (база данных)
```

## ⚠️ Важные файлы:

- `vps-key.pem` - SSH ключ (НЕ добавлять в Git!)
- `.env.production` - Реальные токены (НЕ добавлять в Git!)
- `deploy-to-vps.sh` - Скрипт деплоя
- `.gitignore` - Защищает секретные файлы

## 🎯 Первый запуск:

После успешного деплоя протестируйте бота:
1. Откройте Telegram
2. Найдите вашего бота
3. Отправьте `/start`
4. Проверьте что бот отвечает

**Готово! Ваш бот работает в продакшене! 🎉**