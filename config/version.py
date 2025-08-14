"""
Версионирование FACEIT Telegram Bot
"""
import os
from pathlib import Path

def get_version() -> str:
    """Получить текущую версию бота из файла VERSION"""
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        if version_file.exists():
            return version_file.read_text().strip()
        return "1.0.0"
    except Exception:
        return "1.0.0"

def get_build_info() -> dict:
    """Получить информацию о сборке"""
    version = get_version()
    
    return {
        "version": version,
        "name": "FACEIT Telegram Bot",
        "description": "Анализ статистики FACEIT игроков",
        "author": "Claude Code",
        "python_version": "3.11+",
        "docker_ready": True
    }

# Экспортируем для использования
__version__ = get_version()
BUILD_INFO = get_build_info()