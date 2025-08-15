"""Additional formatting methods for MessageFormatter."""

from typing import Dict
import logging

logger = logging.getLogger(__name__)


def format_player_playstyle(stats: dict) -> str:
    """Analyze and format player playstyle based on stats."""
    try:
        lifetime = stats.get("lifetime", {})
        
        # Extract key metrics
        kd = float(lifetime.get('Average K/D Ratio', '1.0'))
        kr = float(lifetime.get('Average K/R Ratio', '0.68'))
        hs_percent = float(lifetime.get('Average Headshots %', '45'))
        kpr = float(lifetime.get('Average Kills Per Round', '0.68'))
        
        text = "🎯 <b>Анализ стиля игры</b>\n\n"
        
        # Determine playstyle
        playstyle = ""
        strengths = []
        weaknesses = []
        
        # Aggression level
        if kr > 0.75:
            playstyle = "⚔️ <b>Агрессивный стиль</b>"
            strengths.append("• Активная игра на опережение")
            strengths.append("• Создание пространства для команды")
            if kd < 1.0:
                weaknesses.append("• Частые смерти из-за агрессии")
        elif kr < 0.60:
            playstyle = "🛡️ <b>Пассивный стиль</b>"
            strengths.append("• Удержание позиций")
            strengths.append("• Игра от защиты")
            weaknesses.append("• Мало импакта в раундах")
        else:
            playstyle = "⚖️ <b>Сбалансированный стиль</b>"
            strengths.append("• Адаптация под ситуацию")
            strengths.append("• Универсальность")
        
        text += f"{playstyle}\n\n"
        
        # Aim style
        text += "🎯 <b>Стиль стрельбы:</b>\n"
        if hs_percent > 55:
            text += "• Отличная точность (высокий HS%)\n"
            text += "• Фокус на прицеливание в голову\n"
        elif hs_percent < 40:
            text += "• Спрей-контроль\n"
            text += "• Нужно работать над точностью\n"
        else:
            text += "• Средняя точность\n"
            text += "• Сбалансированная стрельба\n"
        
        text += "\n"
        
        # Role suggestion
        text += "🎮 <b>Рекомендуемые роли:</b>\n"
        if kr > 0.75 and kd > 1.1:
            text += "• Entry Fragger\n"
            text += "• Агрессивный Rifler\n"
        elif hs_percent > 55 and kd > 1.2:
            text += "• AWPer\n"
            text += "• Дальние позиции\n"
        elif kr < 0.60 and kd > 1.0:
            text += "• Support\n"
            text += "• Anchor (удержание сайта)\n"
        else:
            text += "• Rifler\n"
            text += "• Flex (гибкая роль)\n"
        
        text += "\n"
        
        # Strengths and weaknesses
        if strengths:
            text += "💪 <b>Сильные стороны:</b>\n"
            for s in strengths:
                text += f"{s}\n"
        
        if weaknesses:
            text += "\n⚠️ <b>Зоны роста:</b>\n"
            for w in weaknesses:
                text += f"{w}\n"
        
        # Performance rating
        text += "\n📊 <b>Общая оценка:</b> "
        overall_score = (kd * 40 + kr * 30 + hs_percent/100 * 30)
        if overall_score > 50:
            text += "⭐⭐⭐⭐⭐ Отлично"
        elif overall_score > 40:
            text += "⭐⭐⭐⭐ Хорошо"
        elif overall_score > 30:
            text += "⭐⭐⭐ Средне"
        else:
            text += "⭐⭐ Нужна практика"
        
        return text
        
    except Exception as e:
        logger.error(f"Error analyzing playstyle: {e}")
        return "❌ Ошибка при анализе стиля игры"