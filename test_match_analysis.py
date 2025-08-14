#!/usr/bin/env python3
"""
Простой тест для проверки системы анализа матчей.
Запустите этот файл для тестирования основных функций.
"""

import asyncio
import sys
from utils.match_analyzer import MatchAnalyzer, format_match_analysis
from utils.map_analyzer import MapAnalyzer, WeaponAnalyzer
from faceit.api import FaceitAPI

# Тестовые ссылки на матчи FACEIT (замените на реальные)
TEST_URLS = [
    "https://www.faceit.com/en/cs2/room/1-abc123-def456-ghi789",
    "faceit.com/en/cs2/room/test-match-id-123",
    "https://faceit.com/en/cs2/room/another-test-id"
]

def test_url_parsing():
    """Тест парсинга URL."""
    print("🔍 Тестирование парсинга URL...")
    
    faceit_api = FaceitAPI()
    analyzer = MatchAnalyzer(faceit_api)
    
    test_cases = [
        "https://www.faceit.com/en/cs2/room/1-abc123-def456-ghi789",
        "https://faceit.com/en/cs2/room/abc123-def456-ghi789", 
        "faceit.com/en/cs2/room/1-test-match-id",
        "invalid-url",
        "https://google.com"
    ]
    
    for url in test_cases:
        match_id = analyzer.parse_faceit_url(url)
        status = "✅" if match_id else "❌"
        print(f"{status} URL: {url[:50]}... -> ID: {match_id}")
    
    print()

def test_map_analyzer():
    """Тест анализатора карт."""
    print("🗺️ Тестирование анализатора карт...")
    
    # Тест нормализации названий карт
    test_maps = ["mirage", "de_dust2", "Inferno", "de_vertigo", "unknown_map"]
    
    for map_name in test_maps:
        normalized = MapAnalyzer._normalize_map_name(map_name)
        display_name = MapAnalyzer.MAP_POOL.get(normalized, normalized)
        print(f"📍 {map_name} -> {normalized} ({display_name})")
    
    print()

def test_weapon_analyzer():
    """Тест анализатора оружия и стилей."""
    print("⚔️ Тестирование анализатора стилей игры...")
    
    # Тестовые данные для определения роли
    test_stats = [
        {"avg_kd": 1.5, "avg_adr": 85, "avg_hs_rate": 55, "desc": "Потенциальный AWPer"},
        {"avg_kd": 1.2, "avg_adr": 78, "avg_hs_rate": 45, "desc": "Entry Fragger"},
        {"avg_kd": 0.8, "avg_adr": 65, "avg_hs_rate": 40, "desc": "Support"},
        {"avg_kd": 1.1, "avg_adr": 72, "avg_hs_rate": 42, "desc": "Rifler"}
    ]
    
    for stats in test_stats:
        role = WeaponAnalyzer._determine_role(
            stats["avg_kd"], stats["avg_adr"], stats["avg_hs_rate"], 3, 10, 2
        )
        aggression = WeaponAnalyzer._determine_aggression(
            stats["avg_kd"], stats["avg_adr"], 3, 10, 2
        )
        print(f"🎯 {stats['desc']}: {role} ({aggression})")
    
    print()

async def test_match_analysis_flow():
    """Тест полного цикла анализа матча."""
    print("⚔️ Тестирование полного анализа матча...")
    
    faceit_api = FaceitAPI()
    analyzer = MatchAnalyzer(faceit_api)
    
    # Тест с тестовой ссылкой
    test_url = "https://www.faceit.com/en/cs2/room/1-test-match-id"
    
    print(f"🔍 Тестирование анализа: {test_url}")
    
    try:
        result = await analyzer.analyze_match(test_url)
        
        if result.get("success"):
            print("✅ Анализ успешно выполнен!")
            
            # Проверка структуры результата
            required_keys = ["match", "team_analyses", "insights"]
            for key in required_keys:
                if key in result:
                    print(f"✅ Найден ключ: {key}")
                else:
                    print(f"❌ Отсутствует ключ: {key}")
            
            # Тест форматирования
            formatted = format_match_analysis(result)
            print(f"📄 Длина форматированного сообщения: {len(formatted)} символов")
            
        else:
            error = result.get("error", "Неизвестная ошибка")
            print(f"❌ Ошибка анализа: {error}")
            
            # Это нормально для тестовой ссылки
            if "не найден" in error.lower() or "извлечь" in error.lower():
                print("ℹ️ Это ожидаемая ошибка для тестовой ссылки")
    
    except Exception as e:
        print(f"❌ Исключение при анализе: {e}")
    
    print()

def test_data_structures():
    """Тест структур данных."""
    print("📊 Тестирование структур данных...")
    
    # Импорт для тестирования
    from utils.match_analyzer import PlayerAnalysis, TeamAnalysis
    from faceit.models import FaceitPlayer
    
    # Создание тестового игрока
    test_player_data = {
        "player_id": "test-id",
        "nickname": "TestPlayer",
        "avatar": "",
        "country": "RU",
        "games": {}
    }
    
    try:
        test_player = FaceitPlayer(**test_player_data)
        player_analysis = PlayerAnalysis(test_player)
        
        print(f"✅ PlayerAnalysis создан для: {test_player.nickname}")
        print(f"   Danger level: {player_analysis.danger_level}")
        print(f"   Role: {player_analysis.role}")
        
        # Создание анализа команды
        team_analysis = TeamAnalysis("TestTeam")
        team_analysis.players.append(player_analysis)
        
        print(f"✅ TeamAnalysis создан: {team_analysis.team_name}")
        print(f"   Игроков в команде: {len(team_analysis.players)}")
        
    except Exception as e:
        print(f"❌ Ошибка при создании структур: {e}")
    
    print()

def test_error_handling():
    """Тест обработки ошибок."""
    print("🛠️ Тестирование обработки ошибок...")
    
    faceit_api = FaceitAPI()
    analyzer = MatchAnalyzer(faceit_api)
    
    # Тест с некорректными URL
    error_cases = [
        "",
        None,
        "invalid-url",
        "https://google.com",
        "not-a-url-at-all"
    ]
    
    for case in error_cases:
        try:
            match_id = analyzer.parse_faceit_url(case) if case else None
            if match_id:
                print(f"⚠️ Неожиданно успешный парсинг: {case} -> {match_id}")
            else:
                print(f"✅ Корректно обработана ошибка: {case}")
        except Exception as e:
            print(f"❌ Исключение для {case}: {e}")
    
    print()

async def main():
    """Основная функция тестирования."""
    print("🚀 Запуск тестов системы анализа матчей")
    print("=" * 50)
    
    # Запуск всех тестов
    test_url_parsing()
    test_map_analyzer() 
    test_weapon_analyzer()
    test_data_structures()
    test_error_handling()
    
    # Асинхронные тесты
    await test_match_analysis_flow()
    
    print("=" * 50)
    print("✅ Все тесты завершены!")
    print()
    print("📋 Что протестировано:")
    print("• Парсинг URL FACEIT")
    print("• Нормализация названий карт")
    print("• Определение ролей игроков")
    print("• Создание структур данных")
    print("• Обработка ошибок")
    print("• Полный цикл анализа")
    print()
    print("🎯 Для полного тестирования:")
    print("1. Замените TEST_URLS на реальные ссылки")
    print("2. Проверьте настройки FACEIT API")
    print("3. Запустите бота и попробуйте команду /analyze")

if __name__ == "__main__":
    # Проверка версии Python
    if sys.version_info < (3, 7):
        print("❌ Требуется Python 3.7 или выше")
        sys.exit(1)
    
    # Запуск тестов
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Тестирование прервано пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        sys.exit(1)