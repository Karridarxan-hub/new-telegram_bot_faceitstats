# 🏗️ Техническая архитектура FACEIT Telegram Bot

## 📋 Обзор проекта

**FACEIT Telegram Bot** - это комплексный бот для анализа статистики игроков CS2 на платформе FACEIT с системой подписок, реферальной программой и предматчевым анализом.

### **Основные возможности:**
- 📊 Детальная статистика игроков (HLTV Rating 2.1, KAST, Clutch)
- ⚔️ Анализ матчей перед игрой
- 🗺️ Анализ производительности на картах
- 💎 Система подписок с Telegram Stars
- 🎁 Реферальная программа
- 👥 Административные функции

## 🏗️ Архитектура системы

```
faceit-telegram-bot/
├── bot/                    # Основная логика бота
│   ├── bot.py             # Инициализация и запуск бота
│   └── handlers.py        # Обработчики команд и сообщений
├── config/                # Конфигурация
│   └── settings.py        # Настройки проекта
├── faceit/               # Интеграция с FACEIT API
│   ├── api.py            # Клиент FACEIT API
│   └── models.py         # Модели данных FACEIT
├── utils/                # Утилиты и вспомогательные модули
│   ├── storage.py        # Система хранения данных
│   ├── formatter.py      # Форматирование сообщений
│   ├── subscription.py   # Управление подписками
│   ├── admin.py          # Административные функции
│   ├── payments.py       # Обработка платежей
│   ├── match_analyzer.py # Анализ матчей
│   └── map_analyzer.py   # Анализ карт и стилей
├── docs/                 # Документация
└── tests/               # Тесты
```

## 🔧 Технический стек

### **Основные технологии:**
- **Python 3.9+**: Основной язык разработки
- **aiogram 3.x**: Асинхронный фреймворк для Telegram Bot API
- **aiohttp**: HTTP клиент для API запросов
- **pydantic**: Валидация и сериализация данных
- **asyncio**: Асинхронное программирование

### **Внешние API:**
- **Telegram Bot API**: Основной интерфейс бота
- **FACEIT Data API**: Получение игровых данных
- **Telegram Stars**: Платежная система

### **Хранение данных:**
- **JSON файлы**: Локальное хранение пользовательских данных
- **В памяти**: Кэширование и временные данные

## 📊 Модели данных

### **UserData** (`utils/storage.py`)
```python
class UserData(BaseModel):
    user_id: int                           # Telegram user ID
    faceit_player_id: Optional[str]        # FACEIT player ID
    faceit_nickname: Optional[str]         # FACEIT nickname
    waiting_for_nickname: bool = False     # Состояние ввода никнейма
    last_checked_match_id: Optional[str]   # Последний проверенный матч
    subscription: UserSubscription         # Подписка пользователя
    created_at: datetime                   # Дата создания
    last_activity: datetime                # Последняя активность
```

### **UserSubscription** (`utils/storage.py`)
```python
class UserSubscription(BaseModel):
    tier: SubscriptionTier = SubscriptionTier.FREE     # Тип подписки
    expires_at: Optional[datetime] = None              # Дата истечения
    daily_requests: int = 0                            # Запросы за день
    last_request_date: Optional[date] = None           # Дата последнего запроса
    referred_by: Optional[int] = None                  # Кто пригласил
    referral_code: Optional[str] = None                # Реферальный код
    referrals_count: int = 0                           # Количество приглашений
    payment_method: Optional[str] = None               # Метод оплаты
    auto_renew: bool = False                           # Автопродление
```

### **SubscriptionTier** (`utils/storage.py`)
```python
class SubscriptionTier(str, Enum):
    FREE = "free"        # Бесплатная подписка
    PREMIUM = "premium"  # Premium подписка (199 ⭐)
    PRO = "pro"         # Pro подписка (299 ⭐)
```

## 🎮 FACEIT API интеграция

### **FaceitAPI** (`faceit/api.py`)
```python
class FaceitAPI:
    def __init__(self):
        self.base_url = "https://open.faceit.com/data/v4"
        self.api_key = settings.faceit_api_key
        self.timeout = ClientTimeout(total=30)
    
    # Основные методы:
    async def search_player(nickname: str) -> Optional[FaceitPlayer]
    async def get_player_by_id(player_id: str) -> Optional[FaceitPlayer]
    async def get_player_matches(player_id: str, limit: int) -> List[PlayerMatchHistory]
    async def get_match_details(match_id: str) -> Optional[FaceitMatch]
    async def get_match_stats(match_id: str) -> Optional[MatchStatsResponse]
    async def get_player_stats(player_id: str) -> Optional[Dict[str, Any]]
    async def get_matches_with_stats(player_id: str, limit: int) -> List[tuple]
```

### **Rate Limits:**
- **FACEIT API**: 500 requests per 10 minutes
- **Timeout**: 30 seconds per request
- **Retry logic**: Automatic retry on failures

## 💾 Система хранения

### **DataStorage** (`utils/storage.py`)
```python
class DataStorage:
    def __init__(self, file_path: str = "bot_data.json"):
        self.file_path = file_path
        self.users: Dict[int, UserData] = {}
        self._lock = asyncio.Lock()
    
    # Основные методы:
    async def get_user(user_id: int) -> Optional[UserData]
    async def save_user(user_data: UserData) -> bool
    async def upgrade_subscription(user_id: int, tier: SubscriptionTier, duration_days: int) -> bool
    async def can_make_request(user_id: int) -> bool
    async def increment_request_count(user_id: int) -> None
    async def apply_referral(user_id: int, referral_code: str) -> bool
    async def generate_referral_code(user_id: int) -> str
```

### **Backup система:**
- Автоматическое создание бэкапов при изменениях
- Формат: `bot_data_backup_YYYYMMDD_HHMMSS.json`
- Асинхронные операции с блокировками

## 🎯 Система анализа матчей

### **MatchAnalyzer** (`utils/match_analyzer.py`)
```python
class MatchAnalyzer:
    def __init__(self, faceit_api: FaceitAPI):
        self.api = faceit_api
    
    # Основные методы:
    async def analyze_match(match_url_or_id: str) -> Dict[str, Any]
    def parse_faceit_url(url: str) -> Optional[str]
    async def _analyze_team(players: List, team_name: str) -> TeamAnalysis
    async def _analyze_player(player: FaceitPlayer) -> PlayerAnalysis
```

### **Структуры анализа:**
```python
class PlayerAnalysis:
    player: FaceitPlayer      # Данные игрока
    winrate: float           # Винрейт в %
    avg_kd: float           # Средний K/D
    avg_adr: float          # Средний ADR
    hltv_rating: float      # HLTV Rating 2.1
    form_streak: str        # Форма: "WWLWW"
    danger_level: int       # Уровень опасности 1-5
    role: str               # Роль игрока
    playstyle_data: Dict    # Данные о стиле
    map_stats: Dict         # Статистика по картам
    clutch_stats: Dict      # Клатч статистика

class TeamAnalysis:
    team_name: str          # Название команды
    players: List[PlayerAnalysis]  # Игроки
    avg_elo: int           # Средний ELO
    avg_level: int         # Средний уровень
    strong_maps: List[str]  # Сильные карты
    weak_maps: List[str]   # Слабые карты
```

### **Алгоритмы:**
- **Danger Level**: Комплексная оценка на основе HLTV Rating, винрейта, K/D, формы
- **Role Detection**: Автоматическое определение роли по статистике
- **Map Analysis**: Анализ производительности на картах
- **HLTV Rating 2.1**: Реальный расчёт по официальной формуле

## 💰 Система подписок

### **SubscriptionManager** (`utils/subscription.py`)
```python
class SubscriptionManager:
    # Цены в Telegram Stars
    PRICES = {
        SubscriptionTier.PREMIUM: {"monthly": 199, "yearly": 1999},
        SubscriptionTier.PRO: {"monthly": 299, "yearly": 2999}
    }
    
    # Лимиты (временно все бесплатно)
    LIMITS = {
        SubscriptionTier.FREE: {
            "daily_requests": -1,      # Безлимит
            "matches_history": 200,    # Полный доступ
            "advanced_analytics": True, # Бесплатно
            "notifications": True,     # Бесплатно
            "api_access": True        # Бесплатно
        }
    }
```

### **PaymentManager** (`utils/payments.py`)
```python
class PaymentManager:
    def __init__(self, bot: Bot):
        self.bot = bot
    
    # Основные методы:
    async def create_invoice(user_id: int, tier: SubscriptionTier, duration: str) -> Dict
    async def handle_pre_checkout_query(pre_checkout_query: PreCheckoutQuery) -> bool
    async def handle_successful_payment(user_id: int, payment: SuccessfulPayment) -> bool
```

## 🎁 Реферальная система

### **Механика:**
- **Новый пользователь**: 7 дней Premium бесплатно
- **Приглашающий**: 30 дней Premium за каждого друга
- **Код**: Уникальный 8-символьный код для каждого пользователя
- **Активация**: При первом запуске `/start <referral_code>`

### **Реализация:**
```python
async def apply_referral(user_id: int, referral_code: str) -> bool:
    # Поиск пользователя по коду
    # Проверка валидности
    # Выдача бонусов обеим сторонам
    # Обновление счётчиков
```

## 👑 Административная система

### **AdminManager** (`utils/admin.py`)
```python
class AdminManager:
    ADMIN_USER_IDS = [123456789]  # Настройте ваши ID
    
    # Команды:
    async def get_system_stats() -> Dict
    async def grant_subscription(user_id: int, tier: SubscriptionTier, days: int) -> bool
    async def revoke_subscription(user_id: int) -> bool
    async def get_user_info(user_id: int) -> Dict
```

### **Доступные команды:**
- `/admin_stats` - статистика системы
- `/admin_grant <user_id> <tier> [days]` - выдача подписки
- `/admin_user <user_id>` - информация о пользователе
- `/admin_revoke <user_id>` - отзыв подписки

## 🤖 Обработчики бота

### **Основные команды** (`bot/handlers.py`):
```python
# Базовые команды
/start [referral_code]  # Запуск бота
/setplayer <nickname>   # Привязка FACEIT аккаунта
/help                   # Справка

# Статистика
/profile               # Профиль игрока
/stats                # Детальная статистика
/lastmatch            # Последний матч
/matches [limit]      # История матчей

# Анализ
/analyze <url>        # Анализ матча по ссылке
/today               # Быстрый обзор

# Подписки
/subscription        # Управление подпиской
/referral           # Реферальная программа
```

### **Меню кнопки:**
- 📊 Моя статистика
- 🎮 Последний матч
- 📋 История матчей
- 👤 Профиль
- 📈 Анализ формы
- 🔍 Найти игрока
- ⚔️ Анализ матча
- 💎 Подписка
- ℹ️ Помощь

## 📊 Система метрик

### **MessageFormatter** (`utils/formatter.py`)
```python
class MessageFormatter:
    # Расчёт HLTV Rating 2.1
    @staticmethod
    def _calculate_hltv_rating_from_stats(matches_with_stats, player_id) -> float
    
    # Расчёт KAST
    @staticmethod  
    def _calculate_match_stats_from_api(matches_with_stats, player_id) -> dict
    
    # Анализ тильта
    @staticmethod
    def _analyze_tilt_indicators(matches_with_stats, player_id) -> dict
    
    # Форматирование сообщений
    @staticmethod
    def format_player_info(player, stats, matches) -> str
    def format_match_result(match, stats, player_id) -> str
    def format_detailed_stats(player, stats, matches) -> str
```

### **Ключевые метрики:**
- **HLTV Rating 2.1**: Реальный расчёт по формуле
- **KAST**: Kill/Assist/Survive/Trade percentage
- **ADR**: Average Damage per Round
- **Clutch Rate**: Процент успешных клатчей
- **Impact Rating**: Влияние на исход раунда
- **Tilt Detection**: Определение тильта по паттернам

## 🗺️ Анализ карт

### **MapAnalyzer** (`utils/map_analyzer.py`)
```python
class MapAnalyzer:
    MAP_POOL = {
        'de_mirage': 'Mirage',
        'de_inferno': 'Inferno',
        'de_dust2': 'Dust2',
        'de_vertigo': 'Vertigo',
        'de_nuke': 'Nuke',
        'de_overpass': 'Overpass',
        'de_ancient': 'Ancient',
        'de_anubis': 'Anubis'
    }
    
    @staticmethod
    def analyze_player_maps(matches_with_stats, player_id) -> Dict
    def generate_map_recommendations(team1_maps, team2_maps) -> List[str]
```

### **WeaponAnalyzer** (`utils/map_analyzer.py`)
```python
class WeaponAnalyzer:
    @staticmethod
    def analyze_player_playstyle(matches_with_stats, player_id) -> Dict
    def _determine_role(avg_kd, avg_adr, avg_hs_rate, ...) -> str
    def _determine_aggression(...) -> str
    def _identify_strengths(...) -> List[str]
```

## 🔧 Конфигурация

### **Settings** (`config/settings.py`)
```python
class Settings(BaseSettings):
    # Telegram
    telegram_bot_token: str
    
    # FACEIT API
    faceit_api_key: str
    faceit_api_base_url: str = "https://open.faceit.com/data/v4"
    
    # Хранение
    data_file_path: str = "bot_data.json"
    backup_enabled: bool = True
    
    # Лимиты
    rate_limit_per_minute: int = 10
    max_matches_history: int = 200
    api_timeout: int = 30
    
    class Config:
        env_file = ".env"
```

### **Переменные окружения (.env):**
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
FACEIT_API_KEY=your_faceit_api_key_here
```

## 🚀 Развёртывание

### **Требования:**
```
Python >= 3.9
aiogram >= 3.0
aiohttp >= 3.8
pydantic >= 1.10
```

### **Установка:**
```bash
# Клонирование
git clone <repository>
cd faceit-telegram-bot

# Установка зависимостей
pip install -r requirements.txt

# Настройка конфигурации
cp .env.example .env
# Отредактировать .env файл

# Запуск
python main.py
```

### **Структура запуска:**
```python
# main.py
import asyncio
from bot.bot import FaceitTelegramBot

async def main():
    bot = FaceitTelegramBot()
    await bot.start_polling()

if __name__ == "__main__":
    asyncio.run(main())
```

## 🔒 Безопасность

### **Токены и ключи:**
- Все секретные данные в переменных окружения
- Валидация API ключей при запуске
- Логирование без секретных данных

### **Права доступа:**
- Административные команды только для ADMIN_USER_IDS
- Валидация платежей через payload
- Проверка user_id в критических операциях

### **Rate Limiting:**
- Лимиты запросов к FACEIT API
- Пользовательские лимиты (временно отключены)
- Обработка превышения лимитов

## 📈 Мониторинг

### **Логирование:**
```python
# Уровни логов
logger.info("Successful operation")
logger.warning("Potential issue")
logger.error("Error occurred")

# Ключевые события
- User registration
- Payment processing
- API calls
- Errors and exceptions
```

### **Метрики для отслеживания:**
- Количество активных пользователей
- Конверсия в платные подписки
- Использование API лимитов
- Частота ошибок
- Производительность анализа

## 🧪 Тестирование

### **Автоматические тесты:**
```bash
# Основные тесты
python test_match_analysis.py

# Тесты компонентов
python -m pytest tests/
```

### **Тестовые данные:**
- Мок FACEIT API ответы
- Тестовые пользователи
- Сценарии ошибок

## 📚 Документация

### **Доступная документация:**
- `TECHNICAL_ARCHITECTURE.md` - техническая архитектура (этот файл)
- `MATCH_ANALYSIS_DOCS.md` - документация анализа матчей
- `MATCH_ANALYSIS_API.md` - API документация
- `TESTING_GUIDE.md` - руководство по тестированию
- `SUBSCRIPTION_SETUP.md` - настройка подписок
- `MATCH_ANALYSIS_SUMMARY.md` - итоговая сводка

### **Для разработчиков:**
- Комментарии в коде
- Type hints везде
- Docstrings для всех функций
- Примеры использования

## 🔄 Workflow разработки

### **Добавление новых функций:**
1. Обновить модели данных в `faceit/models.py`
2. Добавить API методы в `faceit/api.py`
3. Создать обработчики в `bot/handlers.py`
4. Обновить форматирование в `utils/formatter.py`
5. Добавить тесты
6. Обновить документацию

### **Интеграция с внешними API:**
1. Создать клиент в отдельном модуле
2. Добавить модели данных
3. Обработка ошибок и rate limits
4. Логирование и мониторинг

### **Расширение аналитики:**
1. Добавить новые метрики в `MessageFormatter`
2. Обновить структуры данных
3. Создать новые анализаторы в `utils/`
4. Интегрировать в `MatchAnalyzer`

## 🎯 Архитектурные принципы

### **Модульность:**
- Каждый компонент имеет четкую ответственность
- Слабая связанность между модулями
- Легкая замена компонентов

### **Асинхронность:**
- Все I/O операции асинхронные
- Параллельная обработка запросов
- Неблокирующая архитектура

### **Расширяемость:**
- Легко добавлять новые команды
- Простая интеграция новых API
- Модульная система анализа

### **Надёжность:**
- Обработка всех типов ошибок
- Graceful degradation
- Автоматическое восстановление

---

## 🚀 Для агентов: как использовать эту документацию

**Эта документация содержит полную техническую информацию о проекте. Используйте её для:**

1. **Понимания архитектуры** перед внесением изменений
2. **Добавления новых функций** с соблюдением существующих паттернов
3. **Отладки проблем** с пониманием всех компонентов
4. **Интеграции с внешними сервисами** по установленным принципам
5. **Расширения аналитики** с учётом текущих алгоритмов

**При работе с проектом всегда:**
- Следуйте существующим паттернам кода
- Обновляйте документацию при изменениях
- Добавляйте тесты для новой функциональности
- Соблюдайте принципы безопасности
- Учитывайте производительность и лимиты API

**Проект готов к дальнейшему развитию! 🎯**