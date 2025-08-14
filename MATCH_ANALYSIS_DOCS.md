# 📋 Документация по анализу матчей FACEIT Telegram Bot

## 🎯 Обзор функциональности

Система анализа матчей предоставляет детальную информацию о предстоящих матчах, включая анализ игроков, команд, карт и тактические рекомендации.

## 🚀 Возможности

### ✅ **Анализ игроков**
- **Базовая статистика**: K/D, ADR, винрейт, HLTV Rating 2.1
- **Форма игрока**: последние 10 матчей (WWLWL формат)
- **Роль и стиль игры**: Entry Fragger, AWPer, Support, Rifler
- **Уровень опасности**: шкала 1-5 ⭐
- **Клатч статистика**: процент успешных клатчей
- **Анализ агрессивности**: Passive, Balanced, Aggressive

### ✅ **Анализ карт**
- **Индивидуальная статистика** по картам для каждого игрока
- **Командная статистика** по картам
- **Рекомендации** по пику/бану карт
- **Сильные и слабые карты** команд

### ✅ **Командный анализ**
- **Средний ELO и уровень** команды
- **Преимущество по ELO** между командами
- **Опасные игроки** и слабые звенья
- **Тактические рекомендации**

## 📖 Использование

### **1. Команда /analyze**
```
/analyze https://www.faceit.com/en/cs2/room/1-abc-def-ghi
```

### **2. Кнопка "⚔️ Анализ матча" в меню**
После нажатия отправьте ссылку на матч FACEIT

### **3. Прямая отправка ссылки**
Просто отправьте ссылку на матч в чат:
```
https://www.faceit.com/en/cs2/room/1-abc-def-ghi
```

### **Поддерживаемые форматы ссылок:**
- `https://www.faceit.com/en/cs2/room/1-abc-def-ghi`
- `https://faceit.com/en/cs2/room/abc-def-ghi`
- `faceit.com/en/cs2/room/1-abc-def-ghi`

## 🔧 Техническая архитектура

### **Основные компоненты:**

```
utils/
├── match_analyzer.py    # Основной анализатор матчей
├── map_analyzer.py      # Анализ карт и стилей игры
└── formatter.py         # Форматирование и расчёты
```

### **Классы и структуры:**

#### **MatchAnalyzer**
Основной класс для анализа матчей
```python
class MatchAnalyzer:
    def __init__(self, faceit_api: FaceitAPI)
    async def analyze_match(self, match_url_or_id: str) -> Dict[str, Any]
    def parse_faceit_url(self, url: str) -> Optional[str]
```

#### **PlayerAnalysis**
Структура данных для анализа игрока
```python
class PlayerAnalysis:
    player: FaceitPlayer
    winrate: float
    avg_kd: float
    avg_adr: float
    hltv_rating: float
    form_streak: str
    danger_level: int  # 1-5
    role: str
    playstyle_data: Dict
    map_stats: Dict
    clutch_stats: Dict
```

#### **TeamAnalysis**
Структура данных для анализа команды
```python
class TeamAnalysis:
    team_name: str
    players: List[PlayerAnalysis]
    avg_elo: int
    avg_level: int
    strong_maps: List[str]
    weak_maps: List[str]
    team_map_stats: Dict
```

## 📊 Алгоритмы анализа

### **1. Расчёт уровня опасности игрока (1-5 шкала)**

```python
def _calculate_danger_level(analysis: PlayerAnalysis) -> int:
    score = 0
    
    # HLTV Rating (макс 2 балла)
    if analysis.hltv_rating >= 1.3: score += 2
    elif analysis.hltv_rating >= 1.1: score += 1
    elif analysis.hltv_rating >= 1.0: score += 0.5
    
    # Винрейт (макс 1.5 балла)
    if analysis.winrate >= 70: score += 1.5
    elif analysis.winrate >= 60: score += 1
    elif analysis.winrate >= 50: score += 0.5
    
    # K/D (макс 1 балл)
    if analysis.avg_kd >= 1.3: score += 1
    elif analysis.avg_kd >= 1.1: score += 0.5
    
    # Форма (макс 0.5 балла)
    recent_wins = analysis.form_streak[:5].count('W')
    if recent_wins >= 4: score += 0.5
    elif recent_wins >= 3: score += 0.3
    
    return min(5, max(1, int(score) + 1))
```

### **2. Определение роли игрока**

```python
def _determine_role(avg_kd, avg_adr, avg_hs_rate, high_kill_rounds, entry_frags):
    if avg_hs_rate > 50 and avg_kd > 1.3:
        return "AWPer/Sniper"
    elif entry_ratio > 0.4 and avg_kd > 1.0:
        return "Entry Fragger"
    elif high_kill_ratio > 0.3 and avg_adr > 75:
        return "Star Player"
    elif avg_kd < 0.9 and avg_adr > 60:
        return "Support"
    else:
        return "Rifler"
```

### **3. Анализ карт**

```python
def analyze_player_maps(matches_with_stats, player_id):
    map_stats = defaultdict(lambda: {
        'matches': 0, 'wins': 0, 'kills': 0, 
        'deaths': 0, 'assists': 0, 'adr': 0.0
    })
    
    # Обработка каждого матча
    for match, stats in matches_with_stats:
        map_name = extract_map_name(match, stats)
        # ... подсчёт статистики
    
    # Расчёт винрейта и средних показателей
    return analyzed_maps
```

### **4. Генерация рекомендаций по картам**

```python
def generate_map_recommendations(team1_maps, team2_maps):
    # Находим сильные/слабые карты команд
    # Генерируем рекомендации типа:
    # "🎯 Играть: Mirage (у противника 30% винрейт)"
    # "❌ Банить: Dust2 (у противника 85% винрейт)"
```

## 📈 Метрики и показатели

### **Основные статистики:**
- **K/D Ratio**: Kills/Deaths
- **ADR**: Average Damage per Round
- **HLTV Rating 2.1**: Комплексный показатель игрока
- **KAST**: Kill/Assist/Survive/Trade percentage
- **Clutch Rate**: Процент выигранных клатчей
- **Winrate**: Процент выигранных матчей

### **Анализ формы:**
- **Form Streak**: Последние 5-10 результатов (W/L)
- **Recent Performance**: Статистика за последние 20 матчей
- **Trend Analysis**: Улучшение/ухудшение формы

### **Командные метрики:**
- **ELO Advantage**: Разница в ELO между командами
- **Team Synergy**: Совместимость игроков (планируется)
- **Map Pool**: Анализ сильных/слабых карт команды

## 🎯 Примеры вывода

### **Краткий анализ:**
```
🔍 Анализ матча перед игрой

🏆 FPL
⚔️ faction1 vs faction2

📊 Уровень команд:
• faction1: 2850 ELO (Уровень 9)
• faction2: 2650 ELO (Уровень 8)

⚡ Преимущество: faction1 (+200 ELO)

💀 ОПАСНЫЕ ИГРОКИ:
• s1mple (AWPer/Sniper) - 1.45 Rating, 78% WR
  📈 Форма: WWWWL | K/D: 1.52

🎯 СЛАБЫЕ ЦЕЛИ:
• player2 - 0.85 Rating, 35% WR
```

### **Детальный анализ команды:**
```
👥 Команда faction1:
💀 s1mple (AWPer/Sniper)
   📊 1.45 HLTV | 1.52 K/D | 78% WR
   🎮 WWWWL | 🎪 Clutch: 67%
   ⚔️ Стиль: Aggressive | Отличный фраггер

😤 ZywOo (Star Player)
   📊 1.32 HLTV | 1.28 K/D | 71% WR
   🎮 LWWWW | 🎪 Clutch: 55%
   ⚔️ Стиль: Balanced | Высокий урон
```

### **Анализ карт:**
```
🗺️ АНАЛИЗ КАРТ:
• 🎯 Играть: Inferno (у противника 30% винрейт)
• ❌ Банить: Mirage (у противника 85% винрейт)
• ✅ Ваша сила: Dust2 (75% винрейт)
```

## 🔍 Диагностика и отладка

### **Логирование:**
```python
logger.info(f"Extracted match ID: {match_id}")
logger.warning(f"Could not extract match ID from URL: {url}")
logger.error(f"FACEIT API error in match analysis: {e}")
```

### **Обработка ошибок:**
- **Неверная ссылка**: "Не удалось извлечь ID матча из ссылки"
- **Матч не найден**: "Матч не найден"
- **Завершённый матч**: "Матч уже завершён"
- **API ошибки**: "Ошибка API FACEIT"

### **Валидация данных:**
- Проверка формата URL
- Валидация match_id
- Проверка статуса матча
- Контроль качества данных API

## ⚡ Производительность

### **Оптимизации:**
- **Параллельные запросы** к API для разных игроков
- **Кэширование** частых запросов (планируется)
- **Лимиты API**: Соблюдение rate limits FACEIT API
- **Таймауты**: 30 секунд на запрос

### **Ограничения:**
- **Размер сообщения**: Автоматическое разделение длинных сообщений
- **API лимиты**: 500 запросов на 10 минут (FACEIT)
- **Матчи**: Анализируются только незавершённые матчи

## 🛠️ Конфигурация

### **Настройки в коде:**
```python
# Лимиты анализа
ANALYSIS_MATCH_LIMIT = 50  # Матчей для анализа игрока
MIN_MAP_MATCHES = 2        # Минимум матчей на карте
DANGER_LEVEL_SCALE = 5     # Максимальный уровень опасности

# Пороги для ролей
AWP_HS_THRESHOLD = 50      # % HS для AWPer
ENTRY_KD_THRESHOLD = 1.0   # K/D для Entry Fragger
SUPPORT_KD_THRESHOLD = 0.9 # Максимальный K/D для Support
```

### **Карты CS2:**
```python
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
```

## 🚧 Планы развития

### **Фаза 2: Автоматическое отслеживание**
- **Background polling** новых матчей пользователей
- **Автоматические уведомления** при обнаружении матча
- **Webhooks** для real-time обновлений (если доступно)

### **Фаза 3: Расширенная аналитика**
- **AI рекомендации** на основе машинного обучения
- **Анализ противников** в режиме реального времени
- **Командная синергия** и совместимость игроков
- **Прогнозирование результатов** матчей

### **Фаза 4: Дополнительные функции**
- **Веб-интерфейс** для детального анализа
- **API для сторонних разработчиков**
- **Интеграция с Discord** серверами
- **Мобильные уведомления**

## 📞 Поддержка

### **Известные проблемы:**
1. **API лимиты FACEIT** могут вызывать задержки
2. **Парсинг карт** зависит от формата данных FACEIT
3. **Клатч статистика** рассчитывается приблизительно

### **Решение проблем:**
- **Проверьте ссылку** на матч
- **Убедитесь**, что матч не завершён
- **Попробуйте позже** при ошибках API
- **Обратитесь в поддержку** при постоянных ошибках

## 🎉 Заключение

Система анализа матчей FACEIT Telegram Bot предоставляет мощные инструменты для анализа предстоящих игр, помогая игрокам принимать обоснованные решения о тактике, выборе карт и понимании сильных/слабых сторон противников.

**Успешной игры! 🚀**