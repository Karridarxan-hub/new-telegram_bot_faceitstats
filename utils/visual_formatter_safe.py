"""Safe visual progress graphics with ASCII-compatible characters for FACEIT Telegram Bot."""

import math
from typing import List, Tuple, Optional, Dict, Any
from functools import lru_cache


class VisualFormatterSafe:
    """Core class for creating visual progress graphics with ASCII-safe characters."""
    
    # FACEIT rank system mapping
    FACEIT_RANKS = {
        1: {"name": "Level 1", "emoji": "●", "color": "⚪", "elo_range": (0, 500)},
        2: {"name": "Level 2", "emoji": "●", "color": "⚪", "elo_range": (501, 750)},
        3: {"name": "Level 3", "emoji": "●", "color": "🟤", "elo_range": (751, 900)},
        4: {"name": "Level 4", "emoji": "●", "color": "🟤", "elo_range": (901, 1050)},
        5: {"name": "Level 5", "emoji": "♦", "color": "🟡", "elo_range": (1051, 1200)},
        6: {"name": "Level 6", "emoji": "♦", "color": "🟡", "elo_range": (1201, 1350)},
        7: {"name": "Level 7", "emoji": "♦", "color": "🟢", "elo_range": (1351, 1530)},
        8: {"name": "Level 8", "emoji": "♦", "color": "🟢", "elo_range": (1531, 1750)},
        9: {"name": "Level 9", "emoji": "★", "color": "🟠", "elo_range": (1751, 2000)},
        10: {"name": "Level 10", "emoji": "★", "color": "🔴", "elo_range": (2001, 9999)}
    }
    
    @staticmethod
    @lru_cache(maxsize=500)
    def create_progress_bar(value: float, max_value: float, length: int = 10, 
                          filled_char: str = "▰", empty_char: str = "▱",
                          show_percentage: bool = True) -> str:
        """Create a visual progress bar with safe Unicode characters."""
        if max_value <= 0:
            return f"{empty_char * length} 0%"
            
        progress = min(1.0, max(0.0, value / max_value))
        filled_length = int(progress * length)
        
        # Use ASCII-safe fallback if needed
        try:
            bar = filled_char * filled_length + empty_char * (length - filled_length)
        except UnicodeEncodeError:
            # Fallback to ASCII characters
            bar = "#" * filled_length + "-" * (length - filled_length)
        
        if show_percentage:
            percentage = int(progress * 100)
            return f"{bar} {percentage}%"
        else:
            return bar
    
    @staticmethod
    @lru_cache(maxsize=200)
    def create_trend_indicator(current: float, previous: float, 
                             neutral_threshold: float = 0.05) -> str:
        """Create trend indicator with safe characters."""
        if previous <= 0:
            return "→ Новый"
        
        change = (current - previous) / previous
        
        if change > neutral_threshold:
            if change > 0.2:
                return "↗↗ Отлично"
            elif change > 0.1:
                return "↗ Растет"
            else:
                return "↗ Улучшение"
        elif change < -neutral_threshold:
            if change < -0.2:
                return "↘↘ Тревога"
            elif change < -0.1:
                return "↘ Падает"
            else:
                return "↘ Снижение"
        else:
            return "→ Стабильно"
    
    @classmethod
    @lru_cache(maxsize=100)
    def get_rank_visual(cls, skill_level: int, elo: int) -> str:
        """Get visual representation of FACEIT rank with safe characters."""
        rank_info = cls.FACEIT_RANKS.get(skill_level, cls.FACEIT_RANKS[1])
        emoji = rank_info["emoji"]
        name = rank_info["name"]
        
        # Calculate progress to next level
        min_elo, max_elo = rank_info["elo_range"]
        if skill_level < 10:
            next_rank = cls.FACEIT_RANKS.get(skill_level + 1)
            if next_rank:
                next_min = next_rank["elo_range"][0]
                progress = min(1.0, max(0.0, (elo - min_elo) / (next_min - min_elo)))
                progress_bar = cls.create_progress_bar(progress, 1.0, 8, "=", "-", False)
                return f"{emoji} <b>{name}</b>\n{progress_bar} {elo} ELO"
        
        return f"{emoji} <b>{name}</b>\n{'=' * 8} {elo} ELO"
    
    @staticmethod
    def create_loading_animation(stage: int, total_stages: int, message: str = "Загрузка") -> str:
        """Create loading animation for long operations with safe characters."""
        # Create progress bar
        progress = stage / total_stages if total_stages > 0 else 0
        bar = VisualFormatterSafe.create_progress_bar(progress, 1.0, 10, "=", "-")
        
        # Simple spinning animation
        spinner_chars = ["|", "/", "-", "\\"]
        spinner = spinner_chars[stage % len(spinner_chars)]
        
        return f"{spinner} {message}... ({stage}/{total_stages})\n{bar}"
    
    @staticmethod
    def create_performance_summary(stats: Dict[str, float]) -> str:
        """Create a comprehensive performance summary with safe visuals."""
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
            level = "★ Элитный"
            emoji = "★"
        elif performance_score >= 70:
            level = "♦ Высокий"
            emoji = "♦"
        elif performance_score >= 55:
            level = "● Хороший"
            emoji = "●"
        elif performance_score >= 40:
            level = "↗ Развивающийся"
            emoji = "↗"
        else:
            level = "→ Начинающий"
            emoji = "→"
        
        # Create visual summary with safe characters
        score_bar = VisualFormatterSafe.create_progress_bar(performance_score, 100, 12, "=", "-")
        
        return (f"{emoji} <b>Общая оценка: {level}</b>\n"
                f"Скор: {performance_score:.0f}/100\n"
                f"{score_bar}\n\n"
                f"• K/D: {kd:.2f}\n"
                f"• Винрейт: {win_rate:.1f}%\n"
                f"• HS%: {hs_rate:.1f}%")


# Utility functions for quick access with safe characters
def safe_progress_bar(value: float, max_value: float) -> str:
    """Quick access to safe progress bar creation."""
    return VisualFormatterSafe.create_progress_bar(value, max_value)

def safe_rank_display(level: int, elo: int) -> str:
    """Quick access to safe rank visualization."""
    return VisualFormatterSafe.get_rank_visual(level, elo)

def safe_trend(current: float, previous: float) -> str:
    """Quick access to safe trend indicator."""
    return VisualFormatterSafe.create_trend_indicator(current, previous)

def safe_loading(stage: int, total: int, msg: str = "Обработка") -> str:
    """Quick access to safe loading animation."""
    return VisualFormatterSafe.create_loading_animation(stage, total, msg)