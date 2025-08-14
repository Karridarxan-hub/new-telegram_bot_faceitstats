# 🔧 API документация: анализ матчей

## 📋 Обзор

Данная документация описывает программный интерфейс (API) для системы анализа матчей FACEIT Telegram Bot.

## 🚀 Основные классы

### **MatchAnalyzer**

Главный класс для анализа матчей FACEIT.

```python
from utils.match_analyzer import MatchAnalyzer
from faceit.api import FaceitAPI

# Инициализация
faceit_api = FaceitAPI()
analyzer = MatchAnalyzer(faceit_api)

# Анализ матча
result = await analyzer.analyze_match("https://faceit.com/en/cs2/room/1-abc-def")
```

#### **Методы:**

##### `analyze_match(match_url_or_id: str) -> Dict[str, Any]`
Анализирует матч и возвращает полный отчёт.

**Параметры:**
- `match_url_or_id`: URL матча FACEIT или ID матча

**Возвращает:**
```python
{
    "success": True,
    "match": FaceitMatch,
    "team_analyses": {
        "faction1": TeamAnalysis,
        "faction2": TeamAnalysis
    },
    "insights": {
        "dangerous_players": List[PlayerAnalysis],
        "weak_targets": List[PlayerAnalysis],
        "elo_advantage": Dict,
        "team_recommendations": List[str],
        "key_matchups": List
    }
}
```

**Пример ошибки:**
```python
{
    "success": False,
    "error": "Матч уже завершён"
}
```

##### `parse_faceit_url(url: str) -> Optional[str]`
Извлекает ID матча из URL FACEIT.

**Параметры:**
- `url`: URL матча FACEIT

**Возвращает:**
- `str`: ID матча или `None` если не удалось извлечь

**Поддерживаемые форматы:**
```python
# Все эти форматы поддерживаются:
urls = [
    "https://www.faceit.com/en/cs2/room/1-abc123-def456-ghi789",
    "https://faceit.com/en/cs2/room/abc123-def456-ghi789", 
    "faceit.com/en/cs2/room/1-abc123-def456-ghi789"
]

for url in urls:
    match_id = analyzer.parse_faceit_url(url)
    print(f"URL: {url} -> ID: {match_id}")
```

### **PlayerAnalysis**

Структура данных для анализа игрока.

```python
class PlayerAnalysis:
    def __init__(self, player: FaceitPlayer):
        self.player = player                    # Объект игрока FACEIT
        self.recent_matches = []               # Последние матчи
        self.match_stats = []                  # Матчи со статистикой
        self.winrate = 0.0                     # Винрейт в %
        self.avg_kd = 0.0                      # Средний K/D
        self.avg_adr = 0.0                     # Средний ADR
        self.hltv_rating = 0.0                 # HLTV Rating 2.1
        self.form_streak = ""                  # Форма: "WWLWW"
        self.preferred_weapons = {}            # Предпочтения по оружию
        self.map_performance = {}              # Статистика по картам
        self.clutch_stats = {}                 # Клатч статистика
        self.danger_level = 0                  # Уровень опасности 1-5
        self.role = "Rifler"                   # Роль игрока
        self.playstyle_data = {}               # Данные о стиле игры
        self.map_stats = {}                    # Детальная статистика по картам
```

**Пример использования:**
```python
# Получение анализа игрока
for team_name, team_analysis in result["team_analyses"].items():
    for player_analysis in team_analysis.players:
        print(f"Игрок: {player_analysis.player.nickname}")
        print(f"K/D: {player_analysis.avg_kd}")
        print(f"Роль: {player_analysis.role}")
        print(f"Опасность: {player_analysis.danger_level}/5")
        print(f"Форма: {player_analysis.form_streak}")
```

### **TeamAnalysis**

Структура данных для анализа команды.

```python
class TeamAnalysis:
    def __init__(self, team_name: str):
        self.team_name = team_name             # Название команды
        self.players = []                      # Список PlayerAnalysis
        self.avg_elo = 0                       # Средний ELO
        self.avg_level = 0                     # Средний уровень
        self.team_synergy = 0.0               # Синергия команды
        self.strong_maps = []                  # Сильные карты
        self.weak_maps = []                    # Слабые карты  
        self.team_map_stats = {}              # Командная статистика по картам
```

**Пример использования:**
```python
# Анализ команды
team = result["team_analyses"]["faction1"]
print(f"Команда: {team.team_name}")
print(f"Средний ELO: {team.avg_elo}")
print(f"Сильные карты: {team.strong_maps}")
print(f"Слабые карты: {team.weak_maps}")

# Сортировка игроков по опасности
team.players.sort(key=lambda x: x.danger_level, reverse=True)
most_dangerous = team.players[0]
print(f"Самый опасный: {most_dangerous.player.nickname}")
```

## 🗺️ MapAnalyzer

Класс для анализа производительности на картах.

### **Методы:**

##### `analyze_player_maps(matches_with_stats: List[Tuple], player_id: str) -> Dict[str, Any]`
Анализирует производительность игрока на разных картах.

**Параметры:**
- `matches_with_stats`: Список кортежей (матч, статистика)
- `player_id`: ID игрока FACEIT

**Возвращает:**
```python
{
    "de_mirage": {
        "matches": 15,
        "winrate": 73.3,
        "avg_kd": 1.24,
        "avg_adr": 82.5,
        "total_kills": 186,
        "total_deaths": 150
    },
    "de_dust2": {
        "matches": 8,
        "winrate": 37.5,
        "avg_kd": 0.89,
        "avg_adr": 65.2,
        "total_kills": 71,
        "total_deaths": 80
    }
}
```

**Пример использования:**
```python
from utils.map_analyzer import MapAnalyzer

# Анализ карт игрока
player_maps = MapAnalyzer.analyze_player_maps(matches_with_stats, player_id)

# Найти лучшую карту
best_map = max(player_maps.items(), key=lambda x: x[1]['winrate'])
print(f"Лучшая карта: {best_map[0]} ({best_map[1]['winrate']}% WR)")

# Найти худшую карту
worst_map = min(player_maps.items(), key=lambda x: x[1]['winrate'])
print(f"Худшая карта: {worst_map[0]} ({worst_map[1]['winrate']}% WR)")
```

##### `generate_map_recommendations(team1_maps: Dict, team2_maps: Dict) -> List[str]`
Генерирует рекомендации по выбору карт.

**Параметры:**
- `team1_maps`: Статистика по картам первой команды
- `team2_maps`: Статистика по картам второй команды

**Возвращает:**
```python
[
    "🎯 Играть: Mirage (у противника 30% винрейт)",
    "❌ Банить: Dust2 (у противника 85% винрейт)",
    "✅ Ваша сила: Inferno (75% винрейт)"
]
```

## ⚔️ WeaponAnalyzer

Класс для анализа стиля игры и предпочтений по оружию.

### **Методы:**

##### `analyze_player_playstyle(matches_with_stats: List[Tuple], player_id: str) -> Dict[str, Any]`
Анализирует стиль игры игрока.

**Возвращает:**
```python
{
    "role": "Entry Fragger",
    "aggression_level": "Aggressive", 
    "positioning": "Aggressive angles",
    "avg_kd": 1.18,
    "avg_adr": 78.5,
    "avg_hs_rate": 47.2,
    "strengths": ["Отличный фраггер", "Точная стрельба"],
    "weaknesses": ["Низкая точность"]
}
```

**Пример использования:**
```python
from utils.map_analyzer import WeaponAnalyzer

# Анализ стиля игры
playstyle = WeaponAnalyzer.analyze_player_playstyle(matches_with_stats, player_id)

print(f"Роль: {playstyle['role']}")
print(f"Агрессивность: {playstyle['aggression_level']}")
print(f"Сильные стороны: {', '.join(playstyle['strengths'])}")

# Определение типа игрока
if "AWP" in playstyle['role']:
    print("🎯 Снайпер - держитесь подальше от углов")
elif playstyle['aggression_level'] == "Aggressive":
    print("⚔️ Агрессивный игрок - ожидайте напора")
```

## 📊 Форматирование результатов

### **format_match_analysis(analysis_result: Dict[str, Any]) -> str**

Форматирует результат анализа в читаемое сообщение для Telegram.

**Пример использования:**
```python
from utils.match_analyzer import format_match_analysis

# Анализ матча
result = await analyzer.analyze_match(match_url)

# Форматирование для отправки пользователю
formatted_message = format_match_analysis(result)

# Отправка в Telegram
await message.answer(formatted_message, parse_mode=ParseMode.HTML)
```

### **Дополнительные форматтеры:**

```python
from utils.map_analyzer import format_map_analysis, format_playstyle_analysis

# Форматирование анализа карт
map_message = format_map_analysis(player_maps, player_nickname)

# Форматирование анализа стиля игры
style_message = format_playstyle_analysis(playstyle_data, player_nickname)
```

## 🔍 Примеры интеграции

### **Простой анализ матча:**

```python
async def simple_match_analysis(match_url: str):
    """Простой пример анализа матча."""
    
    # Инициализация
    faceit_api = FaceitAPI()
    analyzer = MatchAnalyzer(faceit_api)
    
    try:
        # Анализ
        result = await analyzer.analyze_match(match_url)
        
        if not result.get("success"):
            return f"Ошибка: {result.get('error')}"
        
        # Извлечение ключевой информации
        insights = result["insights"]
        dangerous_players = insights["dangerous_players"]
        elo_advantage = insights.get("elo_advantage")
        
        # Формирование краткого отчёта
        report = "🔍 Быстрый анализ:\n\n"
        
        if elo_advantage:
            report += f"⚡ Преимущество: {elo_advantage['favored_team']}\n"
        
        if dangerous_players:
            most_dangerous = dangerous_players[0]
            report += f"💀 Самый опасный: {most_dangerous.player.nickname}\n"
            report += f"   📊 {most_dangerous.hltv_rating:.2f} Rating\n"
        
        return report
        
    except Exception as e:
        return f"Ошибка анализа: {e}"
```

### **Детальный анализ команды:**

```python
async def detailed_team_analysis(match_url: str, team_name: str):
    """Детальный анализ конкретной команды."""
    
    faceit_api = FaceitAPI()
    analyzer = MatchAnalyzer(faceit_api)
    
    result = await analyzer.analyze_match(match_url)
    
    if not result.get("success"):
        return None
    
    # Найти команду
    team_analysis = None
    for name, team in result["team_analyses"].items():
        if team_name.lower() in name.lower():
            team_analysis = team
            break
    
    if not team_analysis:
        return None
    
    # Анализ игроков команды
    team_report = {
        "team_name": team_analysis.team_name,
        "avg_elo": team_analysis.avg_elo,
        "players": []
    }
    
    for player in team_analysis.players:
        player_data = {
            "nickname": player.player.nickname,
            "role": player.playstyle_data.get('role', player.role),
            "danger_level": player.danger_level,
            "stats": {
                "kd": player.avg_kd,
                "adr": player.avg_adr,
                "hltv_rating": player.hltv_rating,
                "winrate": player.winrate
            },
            "form": player.form_streak[:5],
            "strengths": player.playstyle_data.get('strengths', []),
            "best_maps": []
        }
        
        # Топ карты игрока
        if player.map_stats:
            sorted_maps = sorted(
                player.map_stats.items(), 
                key=lambda x: x[1]['winrate'], 
                reverse=True
            )
            player_data["best_maps"] = [
                {"map": map_name, "winrate": stats['winrate']} 
                for map_name, stats in sorted_maps[:3]
            ]
        
        team_report["players"].append(player_data)
    
    return team_report
```

### **Мониторинг матчей пользователя:**

```python
async def monitor_user_matches(user_id: int, player_id: str):
    """Мониторинг новых матчей пользователя."""
    
    faceit_api = FaceitAPI()
    analyzer = MatchAnalyzer(faceit_api)
    
    # Получить последние матчи
    recent_matches = await faceit_api.get_player_matches(player_id, limit=5)
    
    for match in recent_matches:
        # Проверить, что матч не завершён
        if match.status.upper() in ["READY", "ONGOING", "CONFIGURING"]:
            
            # Анализировать матч
            result = await analyzer.analyze_match(match.match_id)
            
            if result.get("success"):
                # Отправить анализ пользователю
                formatted_message = format_match_analysis(result)
                
                # Здесь должна быть отправка сообщения в Telegram
                print(f"Новый матч для пользователя {user_id}:")
                print(formatted_message)
                
                break  # Анализируем только первый найденный матч
```

## 🛠️ Обработка ошибок

### **Типы ошибок:**

```python
# Проверка результата анализа
result = await analyzer.analyze_match(match_url)

if not result.get("success"):
    error = result.get("error", "Неизвестная ошибка")
    
    if "не удалось извлечь" in error.lower():
        # Неверный формат URL
        print("Проверьте формат ссылки на матч")
        
    elif "не найден" in error.lower():
        # Матч не существует
        print("Матч с указанным ID не найден")
        
    elif "завершён" in error.lower():
        # Матч уже закончился
        print("Анализ доступен только для незавершённых матчей")
        
    elif "api" in error.lower():
        # Проблемы с API FACEIT
        print("Временные проблемы с сервисом FACEIT")
        
    else:
        print(f"Ошибка: {error}")
```

### **Валидация входных данных:**

```python
def validate_match_url(url: str) -> bool:
    """Проверка корректности URL матча."""
    
    if not url or not isinstance(url, str):
        return False
    
    # Проверить, что это ссылка на FACEIT
    if 'faceit.com' not in url.lower():
        return False
    
    # Проверить, что это ссылка на матч
    if '/room/' not in url.lower():
        return False
    
    return True

# Пример использования
if validate_match_url(user_input):
    result = await analyzer.analyze_match(user_input)
else:
    print("Неверный формат ссылки")
```

## 🚀 Производительность

### **Оптимизация запросов:**

```python
import asyncio

async def analyze_multiple_matches(match_urls: List[str]) -> List[Dict]:
    """Анализ нескольких матчей параллельно."""
    
    faceit_api = FaceitAPI()
    analyzer = MatchAnalyzer(faceit_api)
    
    # Создать задачи для параллельного выполнения
    tasks = [
        analyzer.analyze_match(url) 
        for url in match_urls
    ]
    
    # Выполнить все задачи параллельно
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Обработать результаты
    valid_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Ошибка анализа матча {match_urls[i]}: {result}")
        elif result.get("success"):
            valid_results.append(result)
    
    return valid_results
```

### **Кэширование (пример реализации):**

```python
from datetime import datetime, timedelta
from typing import Dict, Optional

class MatchAnalysisCache:
    """Простой кэш для результатов анализа."""
    
    def __init__(self, ttl_minutes: int = 10):
        self.cache: Dict[str, Dict] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
    
    def get(self, match_id: str) -> Optional[Dict]:
        """Получить из кэша."""
        if match_id in self.cache:
            entry = self.cache[match_id]
            if datetime.now() - entry['timestamp'] < self.ttl:
                return entry['data']
            else:
                del self.cache[match_id]
        return None
    
    def set(self, match_id: str, data: Dict) -> None:
        """Сохранить в кэш."""
        self.cache[match_id] = {
            'data': data,
            'timestamp': datetime.now()
        }

# Использование с кэшем
cache = MatchAnalysisCache(ttl_minutes=15)

async def cached_analyze_match(match_url: str) -> Dict:
    """Анализ матча с кэшированием."""
    
    analyzer = MatchAnalyzer(faceit_api)
    match_id = analyzer.parse_faceit_url(match_url)
    
    # Проверить кэш
    cached_result = cache.get(match_id) if match_id else None
    if cached_result:
        return cached_result
    
    # Выполнить анализ
    result = await analyzer.analyze_match(match_url)
    
    # Сохранить в кэш
    if result.get("success") and match_id:
        cache.set(match_id, result)
    
    return result
```

## 📞 Заключение

Данная API документация предоставляет полное описание системы анализа матчей. Для более детальной информации обращайтесь к исходному коду и основной документации проекта.

**Удачной разработки! 🚀**