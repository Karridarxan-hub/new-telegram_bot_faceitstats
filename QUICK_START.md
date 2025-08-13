# ⚡ Быстрый старт - Запуск бота за 10 минут

## 🎯 Краткий план действий

### 1️⃣ Получите токены (5 минут)

**Telegram Bot Token:**
1. Найдите [@BotFather](https://t.me/botfather) в Telegram
2. `/newbot` → введите имя и username бота
3. **Скопируйте токен**

**FACEIT API Key:**
1. Откройте [developers.faceit.com](https://developers.faceit.com/)
2. Зарегистрируйтесь → создайте приложение
3. **Скопируйте API Key**

### 2️⃣ Настройте проект (3 минуты)

```bash
# Клонируйте репозиторий
git clone <your-repo-url> faceit-bot
cd faceit-bot

# Создайте виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Установите зависимости
pip install -r requirements.txt
```

### 3️⃣ Создайте .env файл (1 минута)

```bash
cp .env.example .env
```

**Отредактируйте .env:**
```env
TELEGRAM_BOT_TOKEN=1234567890:YOUR_BOT_TOKEN_HERE
FACEIT_API_KEY=your-faceit-api-key-here
CHECK_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
```

### 4️⃣ Запустите бота (1 минута)

```bash
python main.py
```

**Увидите:**
```
✅ Configuration validated successfully
🚀 Starting FACEIT Stats Bot...
INFO - Bot started successfully
```

---

## 🚀 Команды для пользователей

Отправьте боту в Telegram:

```
/start           - Приветствие и инструкции
/setplayer s1mple - Привязать FACEIT профиль
/profile         - Показать информацию профиля
/lastmatch       - Последний матч с детальной статистикой
/matches 10      - Последние 10 матчей
/help            - Справка по командам
```

---

## 🛠️ Для продакшена

**Смотрите полную инструкцию в `DEPLOYMENT.md`**

Основные шаги:
1. Настройте systemd service для автозапуска
2. Настройте логирование и мониторинг
3. Создайте backup процедуры
4. Настройте безопасность (firewall, права доступа)

---

## 🆘 Частые проблемы

**Бот не отвечает:**
- Проверьте правильность токенов в .env
- Убедитесь что бот запущен: `python main.py`

**Ошибки API:**
- Проверьте FACEIT API key
- Убедитесь в правильности nickname

**Не находит матчи:**
- Проверьте что есть завершенные матчи на FACEIT
- Увеличьте `CHECK_INTERVAL_MINUTES`

---

**🎮 Готово! Ваш FACEIT бот работает!**