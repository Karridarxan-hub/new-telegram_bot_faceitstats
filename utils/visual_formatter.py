"""Visual progress graphics and UI enhancements for FACEIT Telegram Bot."""

import math
from typing import List, Tuple, Optional, Dict, Any
from functools import lru_cache


class VisualFormatter:
    """Core class for creating visual progress graphics and UI enhancements."""
    
    # FACEIT rank system mapping
    FACEIT_RANKS = {
        1: {"name": "Level 1", "emoji": "🔸", "color": "⚪", "elo_range": (0, 500)},
        2: {"name": "Level 2", "emoji": "🔸", "color": "⚪", "elo_range": (501, 750)},
        3: {"name": "Level 3", "emoji": "🔹", "color": "🟤", "elo_range": (751, 900)},
        4: {"name": "Level 4", "emoji": "🔹", "color": "🟤", "elo_range": (901, 1050)},
        5: {"name": "Level 5", "emoji": "🔶", "color": "🟡", "elo_range": (1051, 1200)},
        6: {"name": "Level 6", "emoji": "🔶", "color": "🟡", "elo_range": (1201, 1350)},
        7: {"name": "Level 7", "emoji": "🔷", "color": "🟢", "elo_range": (1351, 1530)},
        8: {"name": "Level 8", "emoji": "🔷", "color": "🟢", "elo_range": (1531, 1750)},
        9: {"name": "Level 9", "emoji": "🔸", "color": "🟠", "elo_range": (1751, 2000)},
        10: {"name": "Level 10", "emoji": "🔥", "color": "🔴", "elo_range": (2001, 9999)}
    }
    
    @staticmethod
    @lru_cache(maxsize=500)
    def create_progress_bar(value: float, max_value: float, length: int = 10, 
                          filled_char: str = "█", empty_char: str = "░",
                          show_percentage: bool = True) -> str:
        """Create a visual progress bar with Unicode characters."""
        if max_value <= 0:
            return f"{empty_char * length} 0%"
            
        progress = min(1.0, max(0.0, value / max_value))
        filled_length = int(progress * length)
        
        bar = filled_char * filled_length + empty_char * (length - filled_length)
        
        if show_percentage:
            percentage = int(progress * 100)
            return f"{bar} {percentage}%"
        else:
            return bar
    
    @staticmethod
    @lru_cache(maxsize=200)
    def create_trend_indicator(current: float, previous: float, 
                             neutral_threshold: float = 0.05) -> str:
        """Create trend indicator with arrows and colors."""
        if previous <= 0:
            return "➡️ Новый"
        
        change = (current - previous) / previous
        
        if change > neutral_threshold:
            if change > 0.2:
                return "📈🔥 Отлично"
            elif change > 0.1:
                return "📈 Растет"
            else:
                return "📈 Улучшение"
        elif change < -neutral_threshold:
            if change < -0.2:
                return "📉❗ Тревога"
            elif change < -0.1:
                return "📉 Падает"
            else:
                return "📉 Снижение"
        else:
            return "➡️ Стабильно"
    
    @classmethod
    @lru_cache(maxsize=100)
    def get_rank_visual(cls, skill_level: int, elo: int) -> str:
        """Get visual representation of FACEIT rank."""
        rank_info = cls.FACEIT_RANKS.get(skill_level, cls.FACEIT_RANKS[1])
        emoji = rank_info["emoji"]
        color = rank_info["color"]
        name = rank_info["name"]
        
        # Calculate progress to next level
        min_elo, max_elo = rank_info["elo_range"]
        if skill_level < 10:
            next_rank = cls.FACEIT_RANKS.get(skill_level + 1)
            if next_rank:
                next_min = next_rank["elo_range"][0]
                progress = min(1.0, max(0.0, (elo - min_elo) / (next_min - min_elo)))
                progress_bar = cls.create_progress_bar(progress, 1.0, 8, "▰", "▱", False)
                return f"{color}{emoji} <b>{name}</b> {color}\n{progress_bar} {elo} ELO"
        
        return f"{color}{emoji} <b>{name}</b> {color}\n{'▰' * 8} {elo} ELO"
    
    @staticmethod
    @lru_cache(maxsize=300)
    def create_stat_visual(stat_name: str, value: float, benchmark: float,
                          unit: str = "", reverse_good: bool = False) -> str:
        """Create visual representation of a statistic with benchmark comparison."""
        # Determine if value is good compared to benchmark
        is_good = (value < benchmark) if reverse_good else (value > benchmark)
        
        if is_good:
            if value > benchmark * 1.5 or (reverse_good and value < benchmark * 0.5):
                emoji = "🟢🔥"
                status = "Превосходно"
            elif value > benchmark * 1.2 or (reverse_good and value < benchmark * 0.8):
                emoji = "🟢"
                status = "Отлично"
            else:
                emoji = "🟡"
                status = "Хорошо"
        else:
            if value < benchmark * 0.7 or (reverse_good and value > benchmark * 1.3):
                emoji = "🔴"
                status = "Нужно улучшить"
            else:
                emoji = "🟠"
                status = "Средне"
        
        return f"{emoji} <b>{stat_name}:</b> {value:.2f}{unit} ({status})"
    
    @staticmethod
    def create_mini_chart(values: List[float], width: int = 15, height: int = 5) -> str:
        """Create a mini ASCII chart from values."""
        if not values or len(values) < 2:
            return "📊 Недостаточно данных для графика"
        
        # Normalize values to fit chart height
        min_val = min(values)
        max_val = max(values)
        
        if max_val == min_val:
            # All values are the same
            mid_line = "─" * width
            return f"📊 Стабильные показатели\n{mid_line}"
        
        # Create chart lines
        chart_lines = []
        for y in range(height):
            line = ""
            threshold = min_val + (max_val - min_val) * (height - 1 - y) / (height - 1)
            
            for i, value in enumerate(values[-width:]):  # Show last 'width' values
                if value >= threshold:
                    line += "█"
                else:
                    line += " "
            
            chart_lines.append(line)
        
        # Add trend indicator
        trend = "📈" if values[-1] > values[0] else "📉" if values[-1] < values[0] else "➡️"
        
        return f"📊 <b>Тренд {trend}</b>\n" + "\n".join(f"<code>{line}</code>" for line in chart_lines)
    
    @classmethod
    def create_elo_progression_chart(cls, current_elo: int, target_elo: int = None) -> str:
        """Create ELO progression visualization with ranks."""
        if target_elo is None:
            # Find next rank target
            current_level = 1
            for level, info in cls.FACEIT_RANKS.items():
                min_elo, max_elo = info["elo_range"]
                if min_elo <= current_elo <= max_elo:
                    current_level = level
                    break
            
            if current_level < 10:
                target_elo = cls.FACEIT_RANKS[current_level + 1]["elo_range"][0]
            else:
                target_elo = current_elo + 200  # Arbitrary target for Level 10
        
        # Create progression bar
        start_elo = cls.FACEIT_RANKS[current_level]["elo_range"][0]
        progress = (current_elo - start_elo) / (target_elo - start_elo)
        progress_bar = cls.create_progress_bar(progress, 1.0, 12, "▰", "▱")
        
        # Show rank icons
        current_rank = cls.FACEIT_RANKS[current_level]
        next_rank = cls.FACEIT_RANKS.get(current_level + 1, cls.FACEIT_RANKS[10])
        
        return (f"🎯 <b>Прогресс к следующему уровню</b>\n"
                f"{current_rank['emoji']} {current_elo} ELO → {next_rank['emoji']} {target_elo} ELO\n"
                f"{progress_bar}\n"
                f"💪 Осталось: {target_elo - current_elo} ELO")
    
    @staticmethod
    def create_winrate_visual(wins: int, total: int) -> str:
        """Create win rate visualization."""
        if total == 0:
            return "📊 Нет данных о матчах"
        
        win_rate = wins / total * 100
        losses = total - wins
        
        # Color coding
        if win_rate >= 70:
            color = "🟢"
            status = "Отличная серия"
        elif win_rate >= 60:
            color = "🟡"
            status = "Хорошая форма"
        elif win_rate >= 50:
            color = "🟠"
            status = "Средняя форма"
        else:
            color = "🔴"
            status = "Нужно улучшить"
        
        # Create visual bar
        win_ratio = wins / total if total > 0 else 0
        bar_length = 15
        win_blocks = int(win_ratio * bar_length)
        loss_blocks = bar_length - win_blocks
        
        win_bar = "🟩" * win_blocks + "🟥" * loss_blocks
        
        return (f"{color} <b>Винрейт: {win_rate:.1f}%</b> ({status})\n"
                f"{win_bar}\n"
                f"✅ Побед: {wins} | ❌ Поражений: {losses}")
    
    @staticmethod
    def create_kd_trend_chart(kd_values: List[float]) -> str:
        """Create K/D trend visualization."""
        if not kd_values:
            return "📊 Нет данных для анализа K/D"
        
        current_kd = kd_values[-1]
        
        # Determine trend
        if len(kd_values) > 1:
            trend = VisualFormatter.create_trend_indicator(current_kd, kd_values[0])
        else:
            trend = "➡️ Новый"
        
        # Create mini chart
        chart = VisualFormatter.create_mini_chart(kd_values, 12, 4)
        
        # K/D assessment
        if current_kd >= 1.5:
            assessment = "🔥 Выдающийся"
            color = "🟢"
        elif current_kd >= 1.2:
            assessment = "💪 Отличный"
            color = "🟡"
        elif current_kd >= 1.0:
            assessment = "✅ Хороший"
            color = "🟠"
        else:
            assessment = "📚 Развивающийся"
            color = "🔴"
        
        return (f"🎯 <b>K/D Анализ</b>\n"
                f"{color} Текущий: <b>{current_kd:.2f}</b> ({assessment})\n"
                f"{trend}\n\n"
                f"{chart}")
    
    @staticmethod
    def create_loading_animation(stage: int, total_stages: int, message: str = "Загрузка") -> str:
        """Create loading animation for long operations."""
        # Create progress bar
        progress = stage / total_stages if total_stages > 0 else 0
        bar = VisualFormatter.create_progress_bar(progress, 1.0, 10, "▰", "▱")
        
        # Spinning animation
        spinner_chars = ["◐", "◓", "◑", "◒"]
        spinner = spinner_chars[stage % len(spinner_chars)]
        
        return f"{spinner} {message}... ({stage}/{total_stages})\n{bar}"
    
    @staticmethod
    def create_performance_summary(stats: Dict[str, float]) -> str:
        """Create a comprehensive performance summary with visuals."""
        kd = stats.get('kd', 0)
        win_rate = stats.get('win_rate', 0)
        hs_rate = stats.get('hs_rate', 0)
        
        # Overall performance score (0-100)
        performance_score = (
            (min(kd, 2.0) / 2.0 * 40) +  # K/D contributes 40%
            (win_rate / 100 * 35) +        # Win rate contributes 35%
            (hs_rate / 100 * 25)           # HS rate contributes 25%
        ) * 100
        
        # Performance level
        if performance_score >= 85:
            level = "🏆 Элитный"
            emoji = "🔥"
        elif performance_score >= 70:
            level = "💎 Высокий"
            emoji = "⭐"
        elif performance_score >= 55:
            level = "🎯 Хороший"
            emoji = "✅"
        elif performance_score >= 40:
            level = "📈 Развивающийся"
            emoji = "🟡"
        else:
            level = "📚 Начинающий"
            emoji = "🔴"
        
        # Create visual summary
        score_bar = VisualFormatter.create_progress_bar(performance_score, 100, 12, "▰", "▱")
        
        return (f"{emoji} <b>Общая оценка: {level}</b>\n"
                f"📊 Скор: {performance_score:.0f}/100\n"
                f"{score_bar}\n\n"
                f"🎯 K/D: {kd:.2f}\n"
                f"🏆 Винрейт: {win_rate:.1f}%\n"
                f"🎪 HS%: {hs_rate:.1f}%")


# Utility functions for quick access
def quick_progress_bar(value: float, max_value: float) -> str:
    """Quick access to progress bar creation."""
    return VisualFormatter.create_progress_bar(value, max_value)

def quick_rank_display(level: int, elo: int) -> str:
    """Quick access to rank visualization."""
    return VisualFormatter.get_rank_visual(level, elo)

def quick_trend(current: float, previous: float) -> str:
    """Quick access to trend indicator."""
    return VisualFormatter.create_trend_indicator(current, previous)

def quick_loading(stage: int, total: int, msg: str = "Обработка") -> str:
    """Quick access to loading animation."""
    return VisualFormatter.create_loading_animation(stage, total, msg)