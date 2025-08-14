"""Subscription management utilities."""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from enum import Enum

from utils.storage import storage, SubscriptionTier, UserData

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """Manages user subscriptions and billing."""
    
    # Subscription prices in Telegram Stars
    PRICES = {
        SubscriptionTier.PREMIUM: {
            "monthly": 199,  # $19.99 ≈ 199 Stars
            "yearly": 1999   # $199.99 ≈ 1999 Stars (2 months free)
        },
        SubscriptionTier.PRO: {
            "monthly": 299,  # $29.99 ≈ 299 Stars
            "yearly": 2999   # $299.99 ≈ 2999 Stars (2 months free)
        }
    }
    
    # Subscription limits (ALL FREE FOR NOW)
    LIMITS = {
        SubscriptionTier.FREE: {
            "daily_requests": -1,  # Unlimited for now
            "matches_history": 200,  # Full access
            "advanced_analytics": True,  # Free access
            "notifications": True,  # Free access
            "api_access": True  # Free access
        },
        SubscriptionTier.PREMIUM: {
            "daily_requests": -1,  # Unlimited
            "matches_history": 200,
            "advanced_analytics": True,
            "notifications": True,
            "api_access": True
        },
        SubscriptionTier.PRO: {
            "daily_requests": -1,  # Unlimited
            "matches_history": 200,
            "advanced_analytics": True,
            "notifications": True,
            "api_access": True
        }
    }
    
    @staticmethod
    async def can_access_feature(user_id: int, feature: str) -> bool:
        """Check if user can access a specific feature."""
        user = await storage.get_user(user_id)
        if not user:
            return False
        
        # Check if subscription is expired
        if (user.subscription.expires_at and 
            user.subscription.expires_at < datetime.now()):
            # Auto-downgrade expired subscription
            await storage.upgrade_subscription(user_id, SubscriptionTier.FREE, 0)
            user.subscription.tier = SubscriptionTier.FREE
        
        limits = SubscriptionManager.LIMITS.get(user.subscription.tier, {})
        return limits.get(feature, False)
    
    @staticmethod
    async def get_user_limits(user_id: int) -> Dict[str, Any]:
        """Get user's subscription limits."""
        user = await storage.get_user(user_id)
        if not user:
            return SubscriptionManager.LIMITS[SubscriptionTier.FREE]
        
        return SubscriptionManager.LIMITS.get(
            user.subscription.tier, 
            SubscriptionManager.LIMITS[SubscriptionTier.FREE]
        )
    
    @staticmethod
    async def format_subscription_status(user_id: int) -> str:
        """Format user's subscription status message."""
        user = await storage.get_user(user_id)
        if not user:
            return "❌ Пользователь не найден"
        
        tier_icons = {
            SubscriptionTier.FREE: "🆓",
            SubscriptionTier.PREMIUM: "⭐",
            SubscriptionTier.PRO: "💎"
        }
        
        tier_names = {
            SubscriptionTier.FREE: "Бесплатная",
            SubscriptionTier.PREMIUM: "Premium",
            SubscriptionTier.PRO: "Pro"
        }
        
        icon = tier_icons.get(user.subscription.tier, "❓")
        name = tier_names.get(user.subscription.tier, "Неизвестная")
        
        message = f"{icon} <b>Подписка: {name}</b>\n\n"
        
        # Subscription details
        if user.subscription.tier != SubscriptionTier.FREE:
            if user.subscription.expires_at:
                expires_str = user.subscription.expires_at.strftime("%d.%m.%Y")
                message += f"📅 <b>Действует до:</b> {expires_str}\n"
                
                days_left = (user.subscription.expires_at - datetime.now()).days
                if days_left > 0:
                    message += f"⏳ <b>Осталось дней:</b> {days_left}\n"
                else:
                    message += "⚠️ <b>Подписка истекла</b>\n"
        
        # Usage statistics
        limits = await SubscriptionManager.get_user_limits(user_id)
        daily_limit = limits["daily_requests"]
        current_usage = user.subscription.daily_requests
        
        if daily_limit == -1:
            message += f"🚀 <b>Запросы:</b> {current_usage} (безлимит)\n"
        else:
            message += f"📊 <b>Запросы сегодня:</b> {current_usage}/{daily_limit}\n"
        
        message += f"🎮 <b>История матчей:</b> до {limits['matches_history']} матчей\n"
        
        # Features
        message += "\n<b>📋 Доступные функции:</b>\n"
        if limits["advanced_analytics"]:
            message += "✅ Расширенная аналитика\n"
        else:
            message += "❌ Расширенная аналитика\n"
            
        if limits["notifications"]:
            message += "✅ Уведомления о матчах\n"
        else:
            message += "❌ Уведомления о матчах\n"
            
        if limits["api_access"]:
            message += "✅ API доступ\n"
        else:
            message += "❌ API доступ\n"
        
        # Referral info
        if user.subscription.referral_code:
            message += f"\n🎁 <b>Реферальный код:</b> <code>{user.subscription.referral_code}</code>\n"
            message += f"👥 <b>Приглашено друзей:</b> {user.subscription.referrals_count}\n"
        
        return message
    
    @staticmethod
    async def format_upgrade_options(user_id: int) -> str:
        """Format subscription upgrade options."""
        user = await storage.get_user(user_id)
        current_tier = user.subscription.tier if user else SubscriptionTier.FREE
        
        message = "💎 <b>Выберите подписку:</b>\n\n"
        
        # Premium option
        if current_tier != SubscriptionTier.PREMIUM:
            message += "⭐ <b>Premium - 199 ⭐ /месяц</b>\n"
            message += "• До 50 матчей в истории\n"
            message += "• 1000 запросов в день\n"
            message += "• Расширенная аналитика\n"
            message += "• Уведомления о матчах\n"
            message += "• Детекция тильта\n\n"
        
        # Pro option
        if current_tier != SubscriptionTier.PRO:
            message += "💎 <b>Pro - 299 ⭐ /месяц</b>\n"
            message += "• До 200 матчей в истории\n"
            message += "• Безлимитные запросы\n"
            message += "• Все функции Premium\n"
            message += "• API доступ\n"
            message += "• Командные функции\n"
            message += "• Приоритетная поддержка\n\n"
        
        message += "🎁 <b>Годовая подписка со скидкой 17%!</b>\n"
        message += "💰 Premium год: 1999 ⭐ (экономия 389 ⭐)\n"
        message += "💎 Pro год: 2999 ⭐ (экономия 589 ⭐)\n\n"
        
        message += "🎯 <b>Приведи друга - получи месяц бесплатно!</b>\n"
        message += "Используй команду /referral для получения кода"
        
        return message
    
    @staticmethod
    async def create_payment_invoice(
        user_id: int, 
        tier: SubscriptionTier, 
        duration: str = "monthly"
    ) -> Dict[str, Any]:
        """Create payment invoice for subscription."""
        if tier not in SubscriptionManager.PRICES:
            raise ValueError(f"Invalid subscription tier: {tier}")
        
        if duration not in ["monthly", "yearly"]:
            raise ValueError(f"Invalid duration: {duration}")
        
        price = SubscriptionManager.PRICES[tier][duration]
        
        tier_names = {
            SubscriptionTier.PREMIUM: "Premium",
            SubscriptionTier.PRO: "Pro"
        }
        
        duration_names = {
            "monthly": "месяц",
            "yearly": "год"
        }
        
        title = f"FACEIT Bot {tier_names[tier]} - {duration_names[duration]}"
        description = f"Подписка {tier_names[tier]} на {duration_names[duration]}"
        
        return {
            "title": title,
            "description": description,
            "payload": f"{tier.value}_{duration}_{user_id}",
            "currency": "XTR",  # Telegram Stars
            "prices": [{"amount": price, "label": title}]
        }
    
    @staticmethod
    async def process_successful_payment(
        user_id: int, 
        payload: str, 
        telegram_payment_charge_id: str
    ) -> bool:
        """Process successful payment and upgrade subscription."""
        try:
            # Parse payload
            parts = payload.split("_")
            if len(parts) != 3:
                logger.error(f"Invalid payment payload: {payload}")
                return False
            
            tier_str, duration, user_id_str = parts
            
            if int(user_id_str) != user_id:
                logger.error(f"User ID mismatch in payment: {user_id} vs {user_id_str}")
                return False
            
            tier = SubscriptionTier(tier_str)
            duration_days = 30 if duration == "monthly" else 365
            
            # Upgrade subscription
            success = await storage.upgrade_subscription(
                user_id=user_id,
                tier=tier,
                duration_days=duration_days,
                payment_method="telegram_stars"
            )
            
            if success:
                logger.info(f"Successfully upgraded user {user_id} to {tier} for {duration_days} days")
                
                # Log payment for analytics
                await SubscriptionManager._log_payment(
                    user_id, tier, duration, telegram_payment_charge_id
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Error processing payment: {e}")
            return False
    
    @staticmethod
    async def _log_payment(
        user_id: int, 
        tier: SubscriptionTier, 
        duration: str, 
        charge_id: str
    ) -> None:
        """Log payment for analytics (implement based on your analytics needs)."""
        # This could write to a separate payments log file or database
        payment_log = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "tier": tier.value,
            "duration": duration,
            "charge_id": charge_id,
            "amount": SubscriptionManager.PRICES[tier][duration]
        }
        
        logger.info(f"Payment logged: {payment_log}")


# Convenience functions
async def check_subscription_access(user_id: int, required_tier: SubscriptionTier) -> bool:
    """Check if user has required subscription tier or higher."""
    user = await storage.get_user(user_id)
    if not user:
        return False
    
    tier_hierarchy = {
        SubscriptionTier.FREE: 0,
        SubscriptionTier.PREMIUM: 1,
        SubscriptionTier.PRO: 2
    }
    
    user_level = tier_hierarchy.get(user.subscription.tier, 0)
    required_level = tier_hierarchy.get(required_tier, 0)
    
    return user_level >= required_level


async def enforce_rate_limit(user_id: int) -> bool:
    """Enforce rate limiting and return True if request is allowed."""
    if not await storage.can_make_request(user_id):
        return False
    
    await storage.increment_request_count(user_id)
    return True