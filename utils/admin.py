"""Administrative utilities for subscription management."""

import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta

from utils.storage import storage, SubscriptionTier, UserData
from utils.subscription import SubscriptionManager

logger = logging.getLogger(__name__)

# Admin user IDs (configure these based on your needs)
ADMIN_USER_IDS = [
    # Add your Telegram user ID here
    # 123456789,  # Replace with actual admin user ID
]


class AdminManager:
    """Administrative tools for managing subscriptions and users."""
    
    @staticmethod
    def is_admin(user_id: int) -> bool:
        """Check if user is admin."""
        return user_id in ADMIN_USER_IDS
    
    @staticmethod
    async def get_system_stats() -> Dict[str, Any]:
        """Get comprehensive system statistics."""
        subscription_stats = await storage.get_subscription_stats()
        all_users = await storage.get_all_users()
        
        # Revenue calculation (approximate)
        monthly_revenue = (
            subscription_stats["premium_users"] * 199 +
            subscription_stats["pro_users"] * 299
        )
        
        # Activity stats
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        active_today = sum(1 for user in all_users 
                          if user.last_active_at and user.last_active_at.date() == today)
        active_week = sum(1 for user in all_users 
                         if user.last_active_at and user.last_active_at.date() >= week_ago)
        
        return {
            **subscription_stats,
            "estimated_monthly_revenue_stars": monthly_revenue,
            "estimated_monthly_revenue_usd": monthly_revenue * 0.1,  # Approximate Stars to USD
            "active_today": active_today,
            "active_week": active_week,
            "conversion_rate": round(
                (subscription_stats["premium_users"] + subscription_stats["pro_users"]) / 
                max(subscription_stats["total_users"], 1) * 100, 2
            ),
            "avg_requests_per_user": round(
                subscription_stats["daily_requests"] / max(subscription_stats["total_users"], 1), 2
            )
        }
    
    @staticmethod
    async def grant_subscription(
        user_id: int, 
        tier: SubscriptionTier, 
        days: int = 30,
        admin_id: int = None
    ) -> bool:
        """Grant subscription to user (admin command)."""
        success = await storage.upgrade_subscription(
            user_id=user_id,
            tier=tier,
            duration_days=days,
            payment_method="admin_grant"
        )
        
        if success:
            logger.info(f"Admin {admin_id} granted {tier} for {days} days to user {user_id}")
        
        return success
    
    @staticmethod
    async def revoke_subscription(user_id: int, admin_id: int = None) -> bool:
        """Revoke user's subscription (admin command)."""
        user = await storage.get_user(user_id)
        if not user:
            return False
        
        user.subscription.tier = SubscriptionTier.FREE
        user.subscription.expires_at = None
        user.subscription.auto_renew = False
        
        await storage.save_user(user)
        logger.info(f"Admin {admin_id} revoked subscription for user {user_id}")
        return True
    
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
            "subscription_tier": user.subscription.tier.value,
            "subscription_expires": user.subscription.expires_at.isoformat() if user.subscription.expires_at else None,
            "daily_requests": user.subscription.daily_requests,
            "total_requests": user.total_requests,
            "referrals_count": user.subscription.referrals_count,
            "referred_by": user.subscription.referred_by,
            "created_at": user.created_at.isoformat(),
            "last_active": user.last_active_at.isoformat() if user.last_active_at else None
        }
    
    @staticmethod
    async def get_payment_analytics() -> Dict[str, Any]:
        """Get payment and conversion analytics."""
        all_users = await storage.get_all_users()
        
        # Referral analytics
        referred_users = [user for user in all_users if user.subscription.referred_by]
        referrer_users = [user for user in all_users if user.subscription.referrals_count > 0]
        
        # Subscription upgrade patterns
        premium_users = [user for user in all_users if user.subscription.tier == SubscriptionTier.PREMIUM]
        pro_users = [user for user in all_users if user.subscription.tier == SubscriptionTier.PRO]
        
        return {
            "referral_stats": {
                "total_referred": len(referred_users),
                "total_referrers": len(referrer_users),
                "avg_referrals_per_referrer": round(
                    sum(user.subscription.referrals_count for user in referrer_users) / 
                    max(len(referrer_users), 1), 2
                )
            },
            "subscription_patterns": {
                "premium_count": len(premium_users),
                "pro_count": len(pro_users),
                "premium_with_referrals": len([u for u in premium_users if u.subscription.referred_by]),
                "pro_with_referrals": len([u for u in pro_users if u.subscription.referred_by])
            }
        }
    
    @staticmethod
    def format_stats_message(stats: Dict[str, Any]) -> str:
        """Format system statistics for admin."""
        message = "📊 <b>Статистика системы</b>\n\n"
        
        message += f"👥 <b>Пользователи:</b>\n"
        message += f"• Всего: {stats['total_users']}\n"
        message += f"• Free: {stats['free_users']}\n"
        message += f"• Premium: {stats['premium_users']}\n"
        message += f"• Pro: {stats['pro_users']}\n"
        message += f"• Конверсия: {stats['conversion_rate']}%\n\n"
        
        message += f"📈 <b>Активность:</b>\n"
        message += f"• Сегодня: {stats['active_today']}\n"
        message += f"• За неделю: {stats['active_week']}\n"
        message += f"• Запросов сегодня: {stats['daily_requests']}\n"
        message += f"• Среднее на пользователя: {stats['avg_requests_per_user']}\n\n"
        
        message += f"💰 <b>Выручка (оценка):</b>\n"
        message += f"• Месяц: {stats['estimated_monthly_revenue_stars']} ⭐\n"
        message += f"• Месяц: ${stats['estimated_monthly_revenue_usd']:.2f}\n"
        
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
        
        message += f"💎 <b>Подписка:</b> {user_info['subscription_tier']}\n"
        
        if user_info['subscription_expires']:
            expires = datetime.fromisoformat(user_info['subscription_expires'])
            message += f"📅 <b>Истекает:</b> {expires.strftime('%d.%m.%Y %H:%M')}\n"
        
        message += f"📊 <b>Запросы:</b> {user_info['daily_requests']} сегодня, {user_info['total_requests']} всего\n"
        
        if user_info['referrals_count'] > 0:
            message += f"👥 <b>Рефералы:</b> {user_info['referrals_count']}\n"
        
        if user_info['referred_by']:
            message += f"🎁 <b>Приглашен:</b> {user_info['referred_by']}\n"
        
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