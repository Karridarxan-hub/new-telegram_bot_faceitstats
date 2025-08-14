# 🔄 Как обновить бота в Docker

## Применение изменений кода

### **Способ 1: Полная пересборка (рекомендуется)**
```bash
cd "C:\Users\karri\OneDrive\Рабочий стол\projects\Telegram bots\faceit-telegram-bot"

# 1. Остановить бота
docker-compose down

# 2. Пересобрать образ с изменениями
docker-compose build faceit-bot

# 3. Запустить с новым кодом
docker-compose up -d faceit-bot
```

### **Способ 2: Быстрое обновление (одной командой)**
```bash
docker-compose up -d --build faceit-bot
```

### **Способ 3: Принудительная пересборка (при проблемах)**
```bash
# Остановить все
docker-compose down

# Удалить старый образ
docker rmi faceit-telegram-bot-faceit-bot

# Собрать заново без кэша
docker-compose build --no-cache faceit-bot

# Запустить
docker-compose up -d faceit-bot
```

## Применение изменений конфигурации

### **Изменения в .env.docker:**
```bash
# Достаточно перезапуска
docker-compose restart faceit-bot
```

### **Изменения в docker-compose.yml:**
```bash
# Остановить и запустить заново
docker-compose down
docker-compose up -d faceit-bot
```

## Проверка обновлений

### **Проверить что используется новый код:**
```bash
# Посмотреть логи запуска
docker-compose logs faceit-bot --tail 20

# Проверить время создания образа
docker images | grep faceit

# Проверить статус
docker-compose ps
```

### **Проверить версию в контейнере:**
```bash
# Зайти в контейнер
docker-compose exec faceit-bot bash

# Посмотреть файлы
ls -la

# Выйти
exit
```

## Типовые сценарии

### **Добавил новую функцию:**
1. Сохранить изменения в код
2. `docker-compose up -d --build faceit-bot`
3. Проверить логи: `docker-compose logs faceit-bot`

### **Изменил переменные окружения:**
1. Отредактировать `.env.docker`
2. `docker-compose restart faceit-bot`

### **Обновил зависимости (requirements.txt):**
1. `docker-compose build --no-cache faceit-bot`
2. `docker-compose up -d faceit-bot`

### **Что-то сломалось:**
1. `docker-compose down`
2. `docker-compose build --no-cache faceit-bot`
3. `docker-compose up -d faceit-bot`
4. `docker-compose logs faceit-bot`

## Мониторинг

### **Постоянное наблюдение за логами:**
```bash
docker-compose logs -f faceit-bot
```

### **Проверка здоровья:**
```bash
docker-compose ps
# Статус должен быть: Up XX seconds (healthy)
```

### **Проверка использования ресурсов:**
```bash
docker stats faceit-telegram-bot
```

## Backup данных

### **Данные бота (JSON файлы):**
```bash
# Автоматически сохраняются в ./data/
# Бэкапы создаются автоматически при изменениях
```

### **Ручной бэкап:**
```bash
# Скопировать данные из контейнера
docker cp faceit-telegram-bot:/home/app/data ./backup-data
```

## Режим разработки (для быстрых изменений)

### **Подключить код как volume (не рекомендуется для продакшна):**
```yaml
# В docker-compose.yml добавить:
volumes:
  - .:/home/app
  - ./data:/home/app/data
```

После этого изменения в коде будут видны сразу, но нужно вручную перезапускать процесс внутри контейнера.