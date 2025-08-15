"""Administrative utilities for user management."""

import logging
import os
from typing import List, Dict, Any
from datetime import datetime, timedelta

from utils.storage import storage, UserData

logger = logging.getLogger(__name__)

# Admin user IDs loaded from environment variables
def get_admin_user_ids() -> List[int]:
    """Get admin user IDs from environment variable."""
    admin_ids_str = os.getenv("ADMIN_USER_IDS", "")
    if not admin_ids_str.strip():
        logger.warning("⚠️ No admin user IDs configured. Admin features will be disabled.")
        return []
    
    try:
        admin_ids = [
            int(uid.strip()) 
            for uid in admin_ids_str.split(",") 
            if uid.strip().isdigit()
        ]
        logger.info(f"✅ Loaded {len(admin_ids)} admin user IDs from environment")
        return admin_ids
    except Exception as e:
        logger.error(f"❌ Error parsing admin user IDs: {e}")
        return []

ADMIN_USER_IDS = get_admin_user_ids()


class AdminManager:
    """Administrative tools for managing users."""
    
    @staticmethod
    def is_admin(user_id: int) -> bool:
        """Check if user is admin."""
        return user_id in ADMIN_USER_IDS
    
    @staticmethod
    async def get_system_stats() -> Dict[str, Any]:
        """Get comprehensive system statistics."""
        user_stats = await storage.get_user_stats()
        all_users = await storage.get_all_users()
        
        # Activity stats
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        active_today = sum(1 for user in all_users 
                          if user.last_active_at and user.last_active_at.date() == today)
        active_week = sum(1 for user in all_users 
                         if user.last_active_at and user.last_active_at.date() >= week_ago)
        
        return {
            **user_stats,
            "active_today": active_today,
            "active_week": active_week,
            "avg_requests_per_user": round(
                user_stats["total_requests"] / max(user_stats["total_users"], 1), 2
            )
        }
    
    @staticmethod
    async def find_user_by_nickname(nickname: str) -> List[UserData]:
        """Find users by FACEIT nickname."""
        all_users = await storage.get_all_users()
        return [user for user in all_users 
                if user.faceit_nickname and nickname.lower() in user.faceit_nickname.lower()]
    
    @staticmethod
    async def get_user_info(user_id: int) -> Dict[str, Any]:
        """Get detailed user information."""
        user = await storage.get_user(user_id)
        if not user:
            return {"error": "User not found"}
        
        return {
            "user_id": user.user_id,
            "faceit_nickname": user.faceit_nickname,
            "total_requests": user.total_requests,
            "created_at": user.created_at.isoformat(),
            "last_active": user.last_active_at.isoformat() if user.last_active_at else None,
            "notifications_enabled": user.notifications_enabled,
            "language": user.language
        }
    
    @staticmethod
    def format_stats_message(stats: Dict[str, Any]) -> str:
        """Format system statistics for admin."""
        message = "📊 <b>Статистика системы</b>\n\n"
        
        message += f"👥 <b>Пользователи:</b>\n"
        message += f"• Всего: {stats['total_users']}\n"
        message += f"• Активные: {stats['active_users']}\n\n"
        
        message += f"📈 <b>Активность:</b>\n"
        message += f"• Сегодня: {stats['active_today']}\n"
        message += f"• За неделю: {stats['active_week']}\n"
        message += f"• Всего запросов: {stats['total_requests']}\n"
        message += f"• Среднее на пользователя: {stats['avg_requests_per_user']}\n\n"
        
        message += f"🎉 <b>Все функции бесплатны!</b>"
        
        return message
    
    @staticmethod
    def format_user_info(user_info: Dict[str, Any]) -> str:
        """Format user information for admin."""
        if "error" in user_info:
            return f"❌ {user_info['error']}"
        
        message = f"👤 <b>Информация о пользователе</b>\n\n"
        message += f"🆔 <b>ID:</b> {user_info['user_id']}\n"
        
        if user_info['faceit_nickname']:
            message += f"🎮 <b>FACEIT:</b> {user_info['faceit_nickname']}\n"
        
        message += f"📊 <b>Всего запросов:</b> {user_info['total_requests']}\n"
        message += f"🌐 <b>Язык:</b> {user_info['language']}\n"
        message += f"🔔 <b>Уведомления:</b> {'✅' if user_info['notifications_enabled'] else '❌'}\n"
        
        created = datetime.fromisoformat(user_info['created_at'])
        message += f"📅 <b>Создан:</b> {created.strftime('%d.%m.%Y %H:%M')}\n"
        
        if user_info['last_active']:
            last_active = datetime.fromisoformat(user_info['last_active'])
            message += f"⏰ <b>Последняя активность:</b> {last_active.strftime('%d.%m.%Y %H:%M')}\n"
        
        return message


# Convenience functions for admin commands
async def admin_only(func):
    """Decorator to restrict functions to admin users only."""
    async def wrapper(user_id: int, *args, **kwargs):
        if not AdminManager.is_admin(user_id):
            return {"error": "Access denied. Admin privileges required."}
        return await func(user_id, *args, **kwargs)
    return wrapper