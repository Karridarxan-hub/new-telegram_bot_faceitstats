"""
Subscription Service implementation with payment management.

Provides comprehensive subscription and payment functionality:
- Subscription tier management and upgrades
- Payment processing with Telegram Stars
- Referral system with rewards
- Usage tracking and rate limiting
- Subscription expiration handling
- Revenue analytics and reporting
- Integration with Telegram payments API
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import uuid

from database.repositories.subscription import (
    SubscriptionRepository, PaymentRepository
)
from database.repositories.user import UserRepository
from database.models import UserSubscription, Payment, SubscriptionTier, PaymentStatus
from utils.redis_cache import stats_cache
from utils.storage import storage as legacy_storage  # Legacy JSON storage
from .base import (
    BaseService, ServiceResult, ServiceError, ValidationError,
    BusinessRuleError, RateLimitError, EventType
)

logger = logging.getLogger(__name__)


class SubscriptionService(BaseService):
    """
    Service for subscription and payment management.
    
    Handles:
    - Subscription tier management and upgrades
    - Payment processing with Telegram Stars
    - Referral system implementation
    - Usage tracking and rate limiting
    - Subscription expiration management
    - Revenue reporting and analytics
    - Integration with external payment providers
    """
    
    # Subscription pricing in Telegram Stars
    PRICING = {
        SubscriptionTier.PREMIUM: {
            "monthly": {"price": 199, "days": 30},
            "yearly": {"price": 1999, "days": 365}
        },
        SubscriptionTier.PRO: {
            "monthly": {"price": 299, "days": 30},
            "yearly": {"price": 2999, "days": 365}
        }
    }
    
    # Subscription limits and features
    TIER_LIMITS = {
        SubscriptionTier.FREE: {
            "daily_requests": 10,
            "matches_history": 20,
            "advanced_analytics": False,
            "notifications": True,
            "api_access": False,
            "priority_support": False
        },
        SubscriptionTier.PREMIUM: {
            "daily_requests": 100,
            "matches_history": 50,
            "advanced_analytics": True,
            "notifications": True,
            "api_access": True,
            "priority_support": False
        },
        SubscriptionTier.PRO: {
            "daily_requests": -1,  # Unlimited
            "matches_history": 200,
            "advanced_analytics": True,
            "notifications": True,
            "api_access": True,
            "priority_support": True
        }
    }
    
    def __init__(
        self,
        subscription_repository: SubscriptionRepository,
        payment_repository: PaymentRepository,
        user_repository: UserRepository,
        cache=None
    ):
        super().__init__(cache or stats_cache)
        self.subscription_repo = subscription_repository
        self.payment_repo = payment_repository
        self.user_repo = user_repository
        
        # Register repositories
        self.register_repository("subscription", subscription_repository)
        self.register_repository("payment", payment_repository)
        self.register_repository("user", user_repository)
    
    # Subscription management
    async def get_user_subscription(
        self,
        telegram_user_id: int,
        include_usage_stats: bool = True
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Get user's subscription details.
        
        Args:
            telegram_user_id: Telegram user ID
            include_usage_stats: Include usage statistics
            
        Returns:
            ServiceResult with subscription data
        """
        try:
            # Get user
            user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Get subscription
            subscription = await self.subscription_repo.get_by_user_id(user.id)
            if not subscription:
                # Create default subscription if missing
                subscription = await self.subscription_repo.create_default_subscription(user.id)
            
            # Build response data
            subscription_data = {
                "tier": subscription.tier.value,
                "expires_at": subscription.expires_at,
                "auto_renew": subscription.auto_renew,
                "payment_method": subscription.payment_method,
                "daily_requests": subscription.daily_requests,
                "last_reset_date": subscription.last_reset_date,
                "referral_code": subscription.referral_code,
                "referrals_count": subscription.referrals_count,
                "referred_by_user_id": subscription.referred_by_user_id,
                "created_at": subscription.created_at,
                "updated_at": subscription.updated_at
            }
            
            # Add tier limits and features
            subscription_data["limits"] = self.TIER_LIMITS.get(
                subscription.tier, 
                self.TIER_LIMITS[SubscriptionTier.FREE]
            )
            
            # Add usage statistics
            if include_usage_stats:
                can_make_request, limits_info = await self.subscription_repo.can_make_request(user.id)
                subscription_data["usage"] = {
                    "can_make_request": can_make_request,
                    "remaining_requests": limits_info.get("remaining", -1),
                    "daily_limit": limits_info.get("daily_limit", -1)
                }
                
                # Calculate days until expiration
                if subscription.expires_at:
                    days_until_expiration = (subscription.expires_at - datetime.now()).days
                    subscription_data["days_until_expiration"] = max(0, days_until_expiration)
            
            return ServiceResult.success_result(subscription_data)
            
        except Exception as e:
            logger.error(f"Error getting user subscription: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to get subscription: {e}", "SUBSCRIPTION_ERROR")
            )
    
    async def create_payment_invoice(
        self,
        telegram_user_id: int,
        tier: SubscriptionTier,
        duration: str = "monthly"
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Create payment invoice for subscription upgrade.
        
        Args:
            telegram_user_id: Telegram user ID
            tier: Target subscription tier
            duration: Subscription duration (monthly/yearly)
            
        Returns:
            ServiceResult with invoice data
        """
        try:
            # Validate parameters
            if tier not in [SubscriptionTier.PREMIUM, SubscriptionTier.PRO]:
                return ServiceResult.validation_error(
                    f"Invalid subscription tier: {tier.value}",
                    "tier"
                )
            
            if duration not in ["monthly", "yearly"]:
                return ServiceResult.validation_error(
                    f"Invalid duration: {duration}",
                    "duration"
                )
            
            # Get user
            user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Get pricing info
            pricing_info = self.PRICING[tier][duration]
            amount = pricing_info["price"]
            duration_days = pricing_info["days"]
            
            # Create payment record
            payment = await self.payment_repo.create_payment(
                user_id=user.id,
                amount=amount,
                subscription_tier=tier,
                subscription_duration=duration,
                duration_days=duration_days,
                description=f"{tier.value.title()} subscription - {duration}",
                payment_payload=f"{tier.value}_{duration}_{telegram_user_id}"
            )
            
            # Create invoice data for Telegram
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
            
            invoice_data = {
                "payment_id": str(payment.id),
                "title": title,
                "description": description,
                "payload": payment.payment_payload,
                "currency": "XTR",  # Telegram Stars
                "prices": [{"amount": amount, "label": title}],
                "tier": tier.value,
                "duration": duration,
                "duration_days": duration_days
            }
            
            return ServiceResult.success_result(
                invoice_data,
                metadata={"payment_id": str(payment.id)}
            )
            
        except Exception as e:
            logger.error(f"Error creating payment invoice: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to create payment invoice: {e}", "INVOICE_ERROR")
            )
    
    async def process_successful_payment(
        self,
        telegram_user_id: int,
        payment_payload: str,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: Optional[str] = None
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Process successful payment and upgrade subscription.
        
        Args:
            telegram_user_id: Telegram user ID
            payment_payload: Payment payload from invoice
            telegram_payment_charge_id: Telegram charge ID
            provider_payment_charge_id: Provider charge ID
            
        Returns:
            ServiceResult with upgrade result
        """
        try:
            # Parse payload
            payload_parts = payment_payload.split("_")
            if len(payload_parts) != 3:
                return ServiceResult.validation_error(
                    f"Invalid payment payload format: {payment_payload}",
                    "payment_payload"
                )
            
            tier_str, duration, user_id_str = payload_parts
            
            # Validate user ID matches
            if int(user_id_str) != telegram_user_id:
                return ServiceResult.business_rule_error(
                    f"User ID mismatch in payment: {telegram_user_id} vs {user_id_str}",
                    "USER_ID_MISMATCH"
                )
            
            # Get user
            user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Parse tier and duration
            tier = SubscriptionTier(tier_str)
            duration_days = self.PRICING[tier][duration]["days"]
            
            # Process payment within transaction
            result, processing_time = await self.measure_performance(
                "process_successful_payment",
                self._process_payment_transaction,
                user.id,
                tier,
                duration,
                duration_days,
                telegram_payment_charge_id,
                provider_payment_charge_id
            )
            
            # Publish payment completed event
            await self.publish_event(
                EventType.PAYMENT_COMPLETED,
                user.id,
                {
                    "tier": tier.value,
                    "duration": duration,
                    "amount": self.PRICING[tier][duration]["price"],
                    "telegram_payment_charge_id": telegram_payment_charge_id
                },
                {"processing_time_ms": processing_time}
            )
            
            return ServiceResult.success_result(
                result,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            logger.error(f"Error processing successful payment: {e}")
            
            # Publish payment failed event
            try:
                user = await self.user_repo.get_by_telegram_id(telegram_user_id)
                if user:
                    await self.publish_event(
                        EventType.PAYMENT_FAILED,
                        user.id,
                        {
                            "error": str(e),
                            "payment_payload": payment_payload,
                            "telegram_payment_charge_id": telegram_payment_charge_id
                        }
                    )
            except:
                pass
            
            return ServiceResult.error_result(
                ServiceError(f"Failed to process payment: {e}", "PAYMENT_PROCESSING_ERROR")
            )
    
    async def _process_payment_transaction(
        self,
        user_id: uuid.UUID,
        tier: SubscriptionTier,
        duration: str,
        duration_days: int,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: Optional[str]
    ) -> Dict[str, Any]:
        """Process payment within database transaction."""
        async with self.get_session() as session:
            # Upgrade subscription
            subscription = await self.subscription_repo.upgrade_subscription(
                user_id=user_id,
                tier=tier,
                duration_days=duration_days,
                payment_method="telegram_stars"
            )
            
            # Find and complete payment record
            user_payments = await self.payment_repo.get_user_payments(
                user_id=user_id,
                limit=10,
                status=PaymentStatus.PENDING
            )
            
            payment = None
            for p in user_payments:
                if (p.subscription_tier == tier and 
                    p.subscription_duration == duration):
                    payment = p
                    break
            
            if payment:
                await self.payment_repo.complete_payment(
                    payment_id=payment.id,
                    telegram_payment_charge_id=telegram_payment_charge_id,
                    provider_payment_charge_id=provider_payment_charge_id
                )
            
            # Clear subscription caches
            await self.invalidate_cache_pattern(f"subscription:*")
            
            return {
                "subscription": {
                    "tier": subscription.tier.value,
                    "expires_at": subscription.expires_at,
                    "duration_days": duration_days
                },
                "payment_completed": payment is not None
            }
    
    # Rate limiting and usage tracking
    async def check_rate_limit(
        self,
        telegram_user_id: int,
        action: str = "general"
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Check if user can make a request based on rate limits.
        
        Args:
            telegram_user_id: Telegram user ID
            action: Action type being checked
            
        Returns:
            ServiceResult with rate limit status
        """
        try:
            # Get user
            user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Check subscription rate limits
            can_make_request, limits_info = await self.subscription_repo.can_make_request(user.id)
            
            if not can_make_request:
                return ServiceResult.error_result(
                    RateLimitError(
                        f"Rate limit exceeded. Daily limit: {limits_info.get('daily_limit', 'unknown')}",
                        retry_after=self._calculate_retry_after()
                    )
                )
            
            # Additional rate limiting based on action type
            if action == "match_analysis":
                # Check specific rate limits for match analysis
                recent_analyses = await self._get_recent_user_analyses(user.id, hours=1)
                max_hourly = self._get_hourly_limit(user.id)
                
                if len(recent_analyses) >= max_hourly:
                    return ServiceResult.error_result(
                        RateLimitError(
                            f"Hourly analysis limit exceeded ({max_hourly}/hour)",
                            retry_after=3600  # 1 hour
                        )
                    )
            
            return ServiceResult.success_result({
                "allowed": True,
                "remaining_requests": limits_info.get("remaining", -1),
                "daily_limit": limits_info.get("daily_limit", -1),
                "tier": limits_info.get("tier", "free")
            })
            
        except Exception as e:
            logger.error(f"Error checking rate limit: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to check rate limit: {e}", "RATE_LIMIT_ERROR")
            )
    
    async def increment_usage(
        self,
        telegram_user_id: int,
        action: str = "general"
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Increment usage counter for user.
        
        Args:
            telegram_user_id: Telegram user ID
            action: Action type being tracked
            
        Returns:
            ServiceResult with updated usage info
        """
        try:
            # Get user
            user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Increment request count
            subscription = await self.subscription_repo.increment_request_count(user.id)
            if not subscription:
                return ServiceResult.error_result(
                    ServiceError("Failed to increment usage", "USAGE_INCREMENT_ERROR")
                )
            
            # Track usage in cache for analytics
            await self._track_usage_analytics(telegram_user_id, action)
            
            return ServiceResult.success_result({
                "daily_requests": subscription.daily_requests,
                "action": action
            })
            
        except Exception as e:
            logger.error(f"Error incrementing usage: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to increment usage: {e}", "USAGE_ERROR")
            )
    
    # Referral system
    async def generate_referral_code(
        self,
        telegram_user_id: int
    ) -> ServiceResult[str]:
        """
        Generate referral code for user.
        
        Args:
            telegram_user_id: Telegram user ID
            
        Returns:
            ServiceResult with referral code
        """
        try:
            # Get user
            user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Generate referral code
            referral_code = await self.subscription_repo.generate_referral_code(user.id)
            if not referral_code:
                return ServiceResult.error_result(
                    ServiceError("Failed to generate referral code", "REFERRAL_GENERATION_ERROR")
                )
            
            return ServiceResult.success_result(referral_code)
            
        except Exception as e:
            logger.error(f"Error generating referral code: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to generate referral code: {e}", "REFERRAL_ERROR")
            )
    
    async def apply_referral_code(
        self,
        telegram_user_id: int,
        referral_code: str
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Apply referral code for user.
        
        Args:
            telegram_user_id: Telegram user ID
            referral_code: Referral code to apply
            
        Returns:
            ServiceResult with referral application result
        """
        try:
            # Validate referral code format
            if not referral_code or len(referral_code) < 6:
                return ServiceResult.validation_error(
                    "Invalid referral code format",
                    "referral_code"
                )
            
            # Get user
            user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Apply referral
            success, error_msg = await self.subscription_repo.apply_referral(
                user.id, referral_code.upper()
            )
            
            if not success:
                return ServiceResult.business_rule_error(
                    error_msg or "Failed to apply referral code",
                    "REFERRAL_APPLICATION_FAILED"
                )
            
            # Publish event
            await self.publish_event(
                EventType.SUBSCRIPTION_UPGRADED,
                user.id,
                {
                    "action": "referral_applied",
                    "referral_code": referral_code,
                    "bonus_tier": SubscriptionTier.PREMIUM.value,
                    "bonus_days": 7
                }
            )
            
            return ServiceResult.success_result({
                "success": True,
                "bonus_tier": SubscriptionTier.PREMIUM.value,
                "bonus_days": 7,
                "message": "Referral code applied successfully! You received 7 days of Premium access."
            })
            
        except Exception as e:
            logger.error(f"Error applying referral code: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to apply referral code: {e}", "REFERRAL_ERROR")
            )
    
    # Subscription expiration management
    async def check_and_expire_subscriptions(self) -> ServiceResult[Dict[str, Any]]:
        """
        Check for and handle expired subscriptions.
        
        Returns:
            ServiceResult with expiration summary
        """
        try:
            expired_subscriptions = await self.subscription_repo.check_and_expire_subscriptions()
            
            # Publish events for expired subscriptions
            for subscription in expired_subscriptions:
                try:
                    user = await self.user_repo.get_by_id(subscription.user_id)
                    if user:
                        await self.publish_event(
                            EventType.SUBSCRIPTION_EXPIRED,
                            user.id,
                            {
                                "previous_tier": subscription.tier.value,
                                "expired_at": subscription.expires_at
                            }
                        )
                except Exception as e:
                    logger.warning(f"Failed to publish expiration event: {e}")
            
            return ServiceResult.success_result({
                "expired_count": len(expired_subscriptions),
                "expired_users": [sub.user_id for sub in expired_subscriptions]
            })
            
        except Exception as e:
            logger.error(f"Error checking expired subscriptions: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to check expired subscriptions: {e}", "EXPIRATION_ERROR")
            )
    
    async def get_expiring_subscriptions(
        self,
        days_ahead: int = 7
    ) -> ServiceResult[List[Dict[str, Any]]]:
        """
        Get subscriptions expiring within specified days.
        
        Args:
            days_ahead: Number of days to look ahead
            
        Returns:
            ServiceResult with list of expiring subscriptions
        """
        try:
            expiring_subscriptions = await self.subscription_repo.get_expiring_subscriptions(days_ahead)
            
            # Format response
            expiring_data = []
            for subscription in expiring_subscriptions:
                user = await self.user_repo.get_by_id(subscription.user_id)
                if user:
                    expiring_data.append({
                        "telegram_user_id": user.user_id,
                        "faceit_nickname": user.faceit_nickname,
                        "tier": subscription.tier.value,
                        "expires_at": subscription.expires_at,
                        "days_remaining": (subscription.expires_at - datetime.now()).days
                    })
            
            return ServiceResult.success_result(expiring_data)
            
        except Exception as e:
            logger.error(f"Error getting expiring subscriptions: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to get expiring subscriptions: {e}", "EXPIRATION_ERROR")
            )
    
    # Analytics and statistics
    async def get_subscription_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Get comprehensive subscription analytics.
        
        Args:
            start_date: Optional start date for analysis
            end_date: Optional end date for analysis
            
        Returns:
            ServiceResult with analytics data
        """
        try:
            # Get subscription statistics
            subscription_stats = await self.subscription_repo.get_subscription_stats()
            
            # Get revenue statistics
            revenue_stats = await self.payment_repo.get_revenue_stats(start_date, end_date)
            
            # Combine analytics
            analytics = {
                "subscription_overview": subscription_stats,
                "revenue_overview": revenue_stats,
                "analysis_period": {
                    "start_date": start_date.isoformat() if start_date else None,
                    "end_date": end_date.isoformat() if end_date else None
                },
                "performance_metrics": self.get_performance_metrics()
            }
            
            return ServiceResult.success_result(analytics)
            
        except Exception as e:
            logger.error(f"Error getting subscription analytics: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to get analytics: {e}", "ANALYTICS_ERROR")
            )
    
    # Helper methods
    def _calculate_retry_after(self) -> int:
        """Calculate seconds until next request allowed."""
        now = datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return int((tomorrow - now).total_seconds())
    
    def _get_hourly_limit(self, user_id: uuid.UUID) -> int:
        """Get hourly limit based on subscription tier."""
        # This would typically check the user's subscription tier
        # For now, return a default limit
        return 5
    
    async def _get_recent_user_analyses(self, user_id: uuid.UUID, hours: int) -> List:
        """Get recent user analyses for rate limiting."""
        # This would typically query match analyses
        # For now, return empty list
        return []
    
    async def _track_usage_analytics(self, telegram_user_id: int, action: str):
        """Track usage in cache for analytics."""
        if not self.cache:
            return
        
        try:
            # Track daily usage
            today = datetime.now().date()
            usage_key = f"usage:{today}:{action}"
            
            current_count = await self.cache.get(usage_key) or 0
            await self.cache.set(usage_key, current_count + 1, 86400)  # 24 hours TTL
            
            # Track user-specific usage
            user_usage_key = f"user_usage:{telegram_user_id}:{today}"
            user_usage = await self.cache.get(user_usage_key) or {}
            if not isinstance(user_usage, dict):
                user_usage = {}
            
            user_usage[action] = user_usage.get(action, 0) + 1
            await self.cache.set(user_usage_key, user_usage, 86400)
            
        except Exception as e:
            logger.warning(f"Failed to track usage analytics: {e}")
    
    # Health check implementation
    async def health_check(self) -> ServiceResult[Dict[str, Any]]:
        """Perform subscription service health check."""
        try:
            health_data = await self._base_health_check()
            
            # Test database connectivity
            try:
                subscription_count = await self.subscription_repo.count()
                payment_count = await self.payment_repo.count()
                health_data["database_status"] = "connected"
                health_data["total_subscriptions"] = subscription_count
                health_data["total_payments"] = payment_count
            except Exception as e:
                health_data["database_status"] = f"error: {e}"
                health_data["status"] = "degraded"
            
            return ServiceResult.success_result(health_data)
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Health check failed: {e}", "HEALTH_CHECK_ERROR")
            )