"""Advanced CS2 statistics formatting with professional metrics and visual enhancements."""

import logging
from functools import lru_cache
from typing import Tuple, Dict, Any, List
from faceit.models import FaceitPlayer
from .visual_formatter import VisualFormatter, quick_progress_bar, quick_rank_display, quick_trend

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1000)
def _calculate_performance_metrics(kd_ratio: float, kr_ratio: float, hs_percent: float, win_rate: float) -> Dict[str, Any]:
    """Cache expensive performance metric calculations."""
    # ADR estimation (Average Damage per Round)
    estimated_adr = int(kd_ratio * 70) if kd_ratio > 0 else 50
    
    # Calculate KAST (Kill, Assist, Survive, Trade) - approximation
    estimated_kast = min(95, max(45, (kd_ratio * 35) + (kr_ratio * 25) + 25))
    
    # Entry frags estimation
    if kd_ratio > 1.2 and kr_ratio > 0.75:
        entry_rate = "Высокий (~25%)"
        entry_emoji = "⚔️"
    elif kd_ratio > 1.0:
        entry_rate = "Средний (~15%)"
        entry_emoji = "🎯"
    else:
        entry_rate = "Низкий (~8%)"
        entry_emoji = "🛡️"
    
    # Clutch success estimation
    if kd_ratio > 1.3:
        clutch_rate = "Отличный (>30%)"
        clutch_emoji = "👑"
    elif kd_ratio > 1.0:
        clutch_rate = "Хороший (~25%)"
        clutch_emoji = "💪"
    else:
        clutch_rate = "Средний (~15%)"
        clutch_emoji = "🤝"
    
    # HLTV 2.0 rating estimation
    kills_per_round = kr_ratio
    survival_rate = max(0.3, min(0.8, (kd_ratio - 0.5) * 0.4 + 0.5))
    hltv_rating = (kills_per_round * 0.7) + (survival_rate * 0.2) + ((hs_percent/100) * 0.1)
    hltv_rating = max(0.5, min(2.0, hltv_rating))
    
    return {
        "estimated_adr": estimated_adr,
        "estimated_kast": estimated_kast,
        "entry_rate": entry_rate,
        "entry_emoji": entry_emoji,
        "clutch_rate": clutch_rate,
        "clutch_emoji": clutch_emoji,
        "hltv_rating": hltv_rating
    }


@lru_cache(maxsize=100)
def _get_role_recommendation(kd_ratio: float, kr_ratio: float, hs_percent: float) -> Tuple[str, str, str, str]:
    """Cache role recommendation logic."""
    if kd_ratio > 1.3 and kr_ratio > 0.80:
        return ("⚔️ <b>Entry Fragger</b> - первые входы", 
                "• Агрессивная игра на T-стороне", 
                "• Создание пространства команде", "entry")
    elif hs_percent > 55 and kd_ratio > 1.1:
        return ("🎯 <b>AWPer/Sniper</b> - снайперская роль", 
                "• Контроль ключевых углов", 
                "• Дальние дистанции", "awper")
    elif kd_ratio > 1.0 and kr_ratio < 0.70:
        return ("🛡️ <b>Support/Anchor</b> - поддержка", 
                "• Удержание сайтов на CT", 
                "• Помощь команде", "support")
    else:
        return ("⚖️ <b>Rifler</b> - универсал", 
                "• Основное оружие", 
                "• Адаптивная игра", "rifler")


def format_cs2_advanced_stats(player: FaceitPlayer, stats: dict) -> str:
    """Format advanced CS2 statistics with professional metrics (optimized)."""
    try:
        if not stats:
            return "❌ Статистика недоступна"
        
        lifetime = stats.get("lifetime", {})
        segments = stats.get("segments", [])
        
        # Extract metrics once for efficiency
        kd_ratio = float(lifetime.get('Average K/D Ratio', '0'))
        kr_ratio = float(lifetime.get('Average K/R Ratio', '0'))
        hs_percent = float(lifetime.get('Average Headshots %', '0'))
        win_rate = float(lifetime.get('Win Rate %', '0'))
        
        # Use cached performance calculations
        metrics = _calculate_performance_metrics(kd_ratio, kr_ratio, hs_percent, win_rate)
        
        # Get visual rank display
        # Получаем данные только из CS2
        cs2_game = player.games.get('cs2')
        if cs2_game:
            skill_level = cs2_game.skill_level
            elo = cs2_game.faceit_elo
        else:
            skill_level = 1
            elo = 1000
        rank_visual = quick_rank_display(skill_level, elo)
        
        # Create visual stats with progress bars
        kd_bar = quick_progress_bar(min(kd_ratio, 3.0), 3.0)  # Cap at 3.0 for better visualization
        hs_bar = quick_progress_bar(hs_percent, 100)
        wr_bar = quick_progress_bar(win_rate, 100)
        adr_bar = quick_progress_bar(min(metrics['estimated_adr'], 120), 120)  # Cap at 120 ADR
        
        # Performance summary
        perf_stats = {
            'kd': kd_ratio,
            'win_rate': win_rate,
            'hs_rate': hs_percent
        }
        performance_summary = VisualFormatter.create_performance_summary(perf_stats)
        
        # Build string efficiently using list and join
        parts = [
            f"🎯 <b>Продвинутая CS2 статистика</b>",
            f"👤 <b>Игрок:</b> {player.nickname}",
            "",
            "🏆 <b>Ранг и ELO:</b>",
            rank_visual,
            "",
            "📊 <b>Основные метрики с прогрессом:</b>",
            f"🎯 <b>K/D:</b> {kd_ratio:.2f}",
            f"   {kd_bar}",
            f"⚔️ <b>K/R:</b> {kr_ratio:.2f}",
            f"💥 <b>ADR:</b> ~{metrics['estimated_adr']}",
            f"   {adr_bar}",
            f"🎪 <b>HS%:</b> {hs_percent:.1f}%",
            f"   {hs_bar}",
            f"🏆 <b>Винрейт:</b> {win_rate:.1f}%",
            f"   {wr_bar}",
            "",
            "🎯 <b>Продвинутые метрики:</b>",
            f"• <b>KAST%:</b> ~{metrics['estimated_kast']:.0f}% (расчётный)",
            f"• <b>Entry Frags:</b> {metrics['entry_emoji']} {metrics['entry_rate']}",
            f"• <b>Clutch успех:</b> {metrics['clutch_emoji']} {metrics['clutch_rate']}",
            "",
            f"⭐ <b>HLTV 2.0 Rating:</b> {metrics['hltv_rating']:.2f}"
        ]
        
        # Rating assessment
        if metrics['hltv_rating'] > 1.3:
            parts.append("🌟 Выдающийся уровень игры")
        elif metrics['hltv_rating'] > 1.1:
            parts.append("🔥 Высокий уровень игры")
        elif metrics['hltv_rating'] > 0.9:
            parts.append("✅ Хороший уровень игры")
        else:
            parts.append("📚 Есть потенциал для роста")
        
        # Performance analysis
        parts.extend([
            "📈 <b>Анализ производительности:</b>",
        ])
        
        total_matches = int(lifetime.get('Matches', '0'))
        
        if win_rate > 60:
            parts.append("🟢 <b>Отличная форма</b> - стабильные победы")
        elif win_rate > 50:
            parts.append("🟡 <b>Хорошая форма</b> - позитивный винрейт")
        else:
            parts.append("🔴 <b>Требует улучшений</b> - работайте над игрой")
            
        parts.extend([
            f"• Всего матчей: {total_matches}",
            f"• Побед: {int(lifetime.get('Wins', '0'))}",
            "",
            "🎮 <b>Рекомендуемая роль:</b>"
        ])
        
        # Use cached role recommendation
        role_info = _get_role_recommendation(kd_ratio, kr_ratio, hs_percent)
        parts.extend([
            role_info[0],
            role_info[1],
            role_info[2]
        ])
        
        # Recent form analysis with visual trends
        if segments:
            recent = segments[0].get("stats", {})
            recent_kd = float(recent.get('K/D Ratio', '0'))
            avg_kd = kd_ratio  # Use already extracted value
            
            # Create trend visualization
            trend_indicator = quick_trend(recent_kd, avg_kd)
            
            # Create K/D trend chart (simulated with current and average)
            kd_trend = VisualFormatter.create_kd_trend_chart([avg_kd * 0.9, avg_kd, recent_kd])
            
            parts.extend([
                "",
                "📊 <b>Анализ текущей формы:</b>",
                f"Последние матчи: {trend_indicator}",
                kd_trend
            ])
        
        # Add overall performance summary
        parts.extend([
            "",
            "📈 <b>Общая оценка производительности:</b>",
            performance_summary
        ])
        
        # ELO progression visualization
        if skill_level < 10:
            elo_progression = VisualFormatter.create_elo_progression_chart(elo)
            parts.extend([
                "",
                elo_progression
            ])
        
        # Personalized recommendations with visual priority
        parts.extend([
            "",
            "💡 <b>Персональные рекомендации:</b>"
        ])
        
        if kd_ratio < 1.0:
            priority_bar = quick_progress_bar(3, 5)  # High priority
            parts.extend([
                f"🔴 <b>Высокий приоритет:</b> {priority_bar}",
                "• 🎯 Улучшайте позиционирование",
                "• 🎪 Тренируйте crosshair placement",
                "• 🗺️ Изучайте карты глубже"
            ])
        elif kd_ratio < 1.2:
            priority_bar = quick_progress_bar(2, 3)  # Medium priority
            parts.extend([
                f"🟡 <b>Средний приоритет:</b> {priority_bar}",
                "• 🧠 Работайте над game sense",
                "• 👥 Улучшайте командную игру",
                "• 💰 Изучайте экономику"
            ])
        else:
            priority_bar = quick_progress_bar(1, 2)  # Low priority
            parts.extend([
                f"🟢 <b>Элитный уровень:</b> {priority_bar}",
                "• 👑 Развивайте лидерские качества",
                "• 🎯 Помогайте команде тактически",
                "• 📺 Изучайте про-сцену"
            ])
        
        # Map-specific advice with visual indicators
        parts.extend([
            "",
            "🗺️ <b>Рекомендуемые карты:</b>"
        ])
        
        if kd_ratio > 1.2:  # Aggressive players
            style_match = quick_progress_bar(4, 5)
            parts.extend([
                f"⚔️ <b>Агрессивный стиль</b> {style_match}",
                "• 🏜️ Dust2 - открытые дуэли",
                "• 🏢 Mirage - мид-контроль",
                "• 🏭 Cache - быстрые раши"
            ])
        elif hs_percent > 50:  # Accurate players  
            style_match = quick_progress_bar(3, 4)
            parts.extend([
                f"🎯 <b>Точная стрельба</b> {style_match}",
                "• 🚂 Train - дальние дуэли",
                "• 🌉 Overpass - вертикальность",
                "• 🏺 Ancient - точность важна"
            ])
        else:  # Tactical players
            style_match = quick_progress_bar(3, 4)
            parts.extend([
                f"🧠 <b>Тактическая игра</b> {style_match}",
                "• 🔥 Inferno - узкие проходы",
                "• ⚛️ Nuke - вертикальная игра",
                "• 🏢 Mirage - командная работа"
            ])
        
        # Join all parts efficiently (much faster than string concatenation)
        return "\n".join(parts)
        
    except Exception as e:
        logger.error(f"Error formatting CS2 advanced stats: {e}")
        return f"❌ Ошибка при форматировании статистики для {player.nickname}"


def format_weapon_stats(stats: dict) -> str:
    """Format weapon-specific statistics with visual enhancements."""
    try:
        lifetime = stats.get("lifetime", {})
        hs_percent = float(lifetime.get('Average Headshots %', '0'))
        kd_ratio = float(lifetime.get('Average K/D Ratio', '0'))
        kr_ratio = float(lifetime.get('Average K/R Ratio', '0'))
        
        # Create weapon proficiency visualization
        rifle_proficiency = min(100, (kd_ratio * 30) + (hs_percent * 0.8))
        awp_proficiency = min(100, (hs_percent * 1.2) + (kd_ratio * 20))
        smg_proficiency = min(100, (kr_ratio * 80) + (kd_ratio * 15))
        
        rifle_bar = quick_progress_bar(rifle_proficiency, 100)
        awp_bar = quick_progress_bar(awp_proficiency, 100)
        smg_bar = quick_progress_bar(smg_proficiency, 100)
        
        text = "🔫 <b>Анализ оружия с визуализацией</b>\n\n"
        
        # Weapon proficiency with bars
        text += "📊 <b>Предполагаемое мастерство:</b>\n"
        text += f"🎯 <b>Rifles (AK/M4):</b> {rifle_proficiency:.0f}%\n"
        text += f"   {rifle_bar}\n"
        text += f"🔭 <b>AWP/Снайперки:</b> {awp_proficiency:.0f}%\n"
        text += f"   {awp_bar}\n"
        text += f"💥 <b>SMG/Пистолеты:</b> {smg_proficiency:.0f}%\n"
        text += f"   {smg_bar}\n\n"
        
        # Weapon recommendations based on stats
        text += "🎯 <b>Рекомендации по оружию:</b>\n"
        
        if hs_percent > 55:
            text += "⭐ <b>Приоритет:</b> AWP и точная стрельба\n"
            text += "• 🔭 Тренируйте AWP позиции\n"
            text += "• 🎯 Развивайте один-тапы\n"
        elif kd_ratio > 1.2:
            text += "⚔️ <b>Приоритет:</b> Агрессивные винтовки\n" 
            text += "• 🔥 Изучайте спрей AK-47\n"
            text += "• 💨 Тренируйте быстрые пики\n"
        else:
            text += "🛡️ <b>Приоритет:</b> Поддержка и утилиты\n"
            text += "• 💣 Изучайте гранаты\n"
            text += "• 🔧 Фокус на командной игре\n"
            
        # Training recommendations with progress tracking
        text += "\n📈 <b>План тренировок:</b>\n"
        aim_progress = quick_progress_bar(min(hs_percent, 80), 80)
        spray_progress = quick_progress_bar(min(kd_ratio * 50, 100), 100)
        
        text += f"🎪 <b>Точность прицела:</b>\n   {aim_progress}\n"
        text += f"🔥 <b>Контроль отдачи:</b>\n   {spray_progress}\n"
        
        return text
        
    except Exception as e:
        logger.error(f"Error formatting weapon stats: {e}")
        return "❌ Ошибка при анализе оружия"


def format_map_specific_progress(stats: dict, map_name: str = None) -> str:
    """Format map-specific progress with visual progress indicators."""
    try:
        lifetime = stats.get("lifetime", {})
        kd_ratio = float(lifetime.get('Average K/D Ratio', '0'))
        win_rate = float(lifetime.get('Win Rate %', '0'))
        total_matches = int(lifetime.get('Matches', '0'))
        
        text = f"🗺️ <b>Визуальный прогресс по картам</b>\n\n"
        
        # CS2 Active Duty maps with visual progress
        maps_data = {
            "Dust2": {"emoji": "🏜️", "difficulty": "Простая", "style": "Агрессия"},
            "Mirage": {"emoji": "🏢", "difficulty": "Средняя", "style": "Универсал"},
            "Inferno": {"emoji": "🔥", "difficulty": "Сложная", "style": "Тактика"},
            "Nuke": {"emoji": "⚛️", "difficulty": "Очень сложная", "style": "Командная"},
            "Overpass": {"emoji": "🌉", "difficulty": "Сложная", "style": "Позиции"},
            "Vertigo": {"emoji": "🏗️", "difficulty": "Средняя", "style": "Вертикаль"},
            "Ancient": {"emoji": "🏺", "difficulty": "Средняя", "style": "Точность"}
        }
        
        text += "📊 <b>Анализ готовности к картам:</b>\n\n"
        
        for map_name, map_info in maps_data.items():
            # Calculate map suitability based on player style
            if map_name in ["Dust2", "Mirage"] and kd_ratio > 1.1:
                suitability = min(95, (kd_ratio * 40) + (win_rate * 0.5))
                status = "🟢"
            elif map_name in ["Inferno", "Nuke"] and win_rate > 55:
                suitability = min(85, (win_rate * 0.8) + (kd_ratio * 30))
                status = "🟡"
            elif map_name in ["Overpass", "Vertigo", "Ancient"]:
                suitability = max(30, min(75, (kd_ratio * 35) + (win_rate * 0.4)))
                status = "🟡" if kd_ratio >= 1.0 else "🔴"
            else:
                suitability = (kd_ratio * 35) + (win_rate * 0.5)
                status = "🟡"
            
            # Create progress bar for map readiness
            map_bar = quick_progress_bar(suitability, 100)
            
            text += f"{map_info['emoji']} <b>{map_name}</b> - {map_info['style']}\n"
            text += f"   Готовность: {status} {suitability:.0f}%\n"
            text += f"   {map_bar}\n\n"
        
        # Overall map pool analysis
        avg_readiness = sum([
            min(95, (kd_ratio * 40) + (win_rate * 0.5)) if map_name in ["Dust2", "Mirage"] else
            min(85, (win_rate * 0.8) + (kd_ratio * 30)) if map_name in ["Inferno", "Nuke"] else
            max(30, min(75, (kd_ratio * 35) + (win_rate * 0.4)))
            for map_name in maps_data.keys()
        ]) / len(maps_data)
        
        overall_bar = quick_progress_bar(avg_readiness, 100)
        text += f"📈 <b>Общая готовность пула:</b> {avg_readiness:.0f}%\n"
        text += f"{overall_bar}\n\n"
        
        # Priority learning recommendations
        text += "🎯 <b>Приоритеты обучения:</b>\n"
        
        if avg_readiness < 50:
            priority_maps = ["Dust2", "Mirage"]
            text += "🔴 <b>Высокий приоритет:</b> Базовые карты\n"
        elif avg_readiness < 75:
            priority_maps = ["Inferno", "Overpass"]
            text += "🟡 <b>Средний приоритет:</b> Тактические карты\n"
        else:
            priority_maps = ["Vertigo", "Ancient"]
            text += "🟢 <b>Низкий приоритет:</b> Новые карты\n"
        
        for priority_map in priority_maps:
            text += f"• {maps_data[priority_map]['emoji']} {priority_map} - {maps_data[priority_map]['style']}\n"
        
        # Training plan with visual progress tracking
        text += "\n📚 <b>План изучения карт:</b>\n"
        weeks_progress = quick_progress_bar(min(total_matches, 100), 100)
        text += f"Опыт в матчах: {total_matches}\n{weeks_progress}\n\n"
        
        text += "💡 <b>Рекомендации:</b>\n"
        text += "• 📺 Смотрите демки профессионалов\n"
        text += "• 💣 Изучайте набор гранат для каждой карты\n"
        text += "• 🗣️ Запоминайте каллауты команды\n"
        text += "• 🎯 Тренируйте позиции в deathmatch\n"
        
        return text
        
    except Exception as e:
        logger.error(f"Error formatting map progress: {e}")
        return "❌ Ошибка при анализе карт с визуализацией"