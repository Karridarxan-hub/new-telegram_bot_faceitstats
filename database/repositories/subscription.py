"""
Subscription Repository implementation with payment management.

Provides subscription and payment functionality including:
- Subscription CRUD operations and tier management
- Payment processing and history tracking
- Referral system management
- Usage limits and rate limiting
- Subscription expiration handling
- Analytics and revenue tracking
"""

import logging
import hashlib
import time
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timedelta
import uuid

from sqlalchemy import select, and_, func, desc, update, or_
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from database.models import (
    UserSubscription, Payment, User, SubscriptionTier, PaymentStatus
)
from database.connection import DatabaseOperationError
from utils.redis_cache import stats_cache
from .base import BaseRepository

logger = logging.getLogger(__name__)


class SubscriptionCreateData:
    """Data class for creating subscriptions."""
    def __init__(
        self,
        user_id: uuid.UUID,
        tier: SubscriptionTier = SubscriptionTier.FREE,
        expires_at: Optional[datetime] = None,
        auto_renew: bool = False,
        payment_method: Optional[str] = None
    ):
        self.user_id = user_id
        self.tier = tier
        self.expires_at = expires_at
        self.auto_renew = auto_renew
        self.payment_method = payment_method


class PaymentCreateData:
    """Data class for creating payments."""
    def __init__(
        self,
        user_id: uuid.UUID,
        amount: int,
        subscription_tier: SubscriptionTier,
        subscription_duration: str,
        duration_days: int,
        description: str,
        telegram_payment_charge_id: Optional[str] = None,
        provider_payment_charge_id: Optional[str] = None,
        payment_payload: Optional[str] = None
    ):
        self.user_id = user_id
        self.amount = amount
        self.subscription_tier = subscription_tier
        self.subscription_duration = subscription_duration
        self.duration_days = duration_days
        self.description = description
        self.telegram_payment_charge_id = telegram_payment_charge_id
        self.provider_payment_charge_id = provider_payment_charge_id
        self.payment_payload = payment_payload


class SubscriptionRepository(BaseRepository[UserSubscription, SubscriptionCreateData, Dict]):
    """
    Repository for UserSubscription entity management.
    
    Provides comprehensive subscription management with:
    - Subscription tier management and upgrades
    - Payment processing and tracking
    - Referral system with bonuses
    - Usage tracking and rate limiting
    - Subscription expiration handling
    - Revenue and analytics tracking
    """
    
    def __init__(self):
        """Initialize subscription repository with Redis cache."""
        super().__init__(UserSubscription, stats_cache)
    
    # Core subscription operations
    async def get_by_user_id(self, user_id: uuid.UUID) -> Optional[UserSubscription]:
        """
        Get subscription by user ID.
        
        Args:
            user_id: User UUID
            
        Returns:
            UserSubscription or None if not found
        """
        cache_key = self._cache_key("user", user_id)
        
        # Try cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            async with self.get_session() as session:
                stmt = select(UserSubscription).where(UserSubscription.user_id == user_id)
                result = await session.execute(stmt)
                subscription = result.scalar_one_or_none()
                
                # Cache result
                if subscription:
                    await self._set_cache(cache_key, subscription, 600)
                
                return subscription
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_by_user_id: {e}")
            raise DatabaseOperationError(f"Failed to get subscription by user id: {e}")
    
    async def get_by_telegram_user_id(self, telegram_user_id: int) -> Optional[UserSubscription]:
        """
        Get subscription by Telegram user ID.
        
        Args:
            telegram_user_id: Telegram user ID
            
        Returns:
            UserSubscription or None if not found
        """
        try:
            async with self.get_session() as session:
                stmt = (
                    select(UserSubscription)
                    .join(User)
                    .where(User.user_id == telegram_user_id)
                )
                result = await session.execute(stmt)
                return result.scalar_one_or_none()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_by_telegram_user_id: {e}")
            raise DatabaseOperationError(f"Failed to get subscription by telegram user id: {e}")
    
    async def create_default_subscription(self, user_id: uuid.UUID) -> UserSubscription:
        """
        Create default FREE subscription for new user.
        
        Args:
            user_id: User UUID
            
        Returns:
            Created subscription
        """
        try:
            async with self.get_session() as session:
                # Check if subscription already exists
                existing = await self.get_by_user_id(user_id)
                if existing:
                    return existing
                
                subscription = UserSubscription(
                    user_id=user_id,
                    tier=SubscriptionTier.FREE,
                    created_at=datetime.now(),
                    last_reset_date=datetime.now().date()
                )
                
                session.add(subscription)
                await session.flush()
                await session.refresh(subscription)
                
                # Invalidate cache
                await self._invalidate_cache("subscriptions:*")
                
                logger.info(f"Created default subscription for user {user_id}")
                return subscription
                
        except IntegrityError as e:
            logger.error(f"Subscription creation integrity error: {e}")
            # Try to get existing subscription
            existing = await self.get_by_user_id(user_id)
            if existing:
                return existing
            raise DatabaseOperationError(f"Failed to create subscription: Duplicate user")
        except SQLAlchemyError as e:
            logger.error(f"Database error in create_default_subscription: {e}")
            raise DatabaseOperationError(f"Failed to create default subscription: {e}")
    
    # Subscription management
    async def upgrade_subscription(
        self,
        user_id: uuid.UUID,
        tier: SubscriptionTier,
        duration_days: int,
        payment_method: str = "telegram_stars"
    ) -> Optional[UserSubscription]:
        """
        Upgrade user subscription to new tier.
        
        Args:
            user_id: User UUID
            tier: New subscription tier
            duration_days: Subscription duration in days
            payment_method: Payment method used
            
        Returns:
            Updated subscription or None if not found
        """
        try:
            async with self.get_session() as session:
                subscription = await self.get_by_user_id(user_id)
                if not subscription:
                    return None
                
                # Calculate expiration date
                if subscription.expires_at and subscription.expires_at > datetime.now():
                    # Extend existing subscription
                    expires_at = subscription.expires_at + timedelta(days=duration_days)
                else:
                    # New subscription
                    expires_at = datetime.now() + timedelta(days=duration_days)
                
                # Update subscription
                subscription.tier = tier
                subscription.expires_at = expires_at
                subscription.payment_method = payment_method
                subscription.auto_renew = True
                subscription.updated_at = datetime.now()
                
                await session.flush()
                await session.refresh(subscription)
                
                # Invalidate caches
                await self._invalidate_cache("subscriptions:*")
                
                logger.info(f"Upgraded subscription for user {user_id} to {tier} until {expires_at}")
                return subscription
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in upgrade_subscription: {e}")
            raise DatabaseOperationError(f"Failed to upgrade subscription: {e}")
    
    async def check_and_expire_subscriptions(self) -> List[UserSubscription]:
        """
        Check for expired subscriptions and downgrade them.
        
        Returns:
            List of expired subscriptions that were downgraded
        """
        try:
            async with self.get_session() as session:
                # Find expired subscriptions
                stmt = (
                    select(UserSubscription)
                    .where(
                        and_(
                            UserSubscription.tier != SubscriptionTier.FREE,
                            UserSubscription.expires_at < datetime.now()
                        )
                    )
                )
                result = await session.execute(stmt)
                expired_subscriptions = result.scalars().all()
                
                downgraded = []
                for subscription in expired_subscriptions:
                    subscription.tier = SubscriptionTier.FREE
                    subscription.expires_at = None
                    subscription.auto_renew = False
                    subscription.updated_at = datetime.now()
                    
                    await session.flush()
                    downgraded.append(subscription)
                
                if downgraded:
                    # Invalidate caches
                    await self._invalidate_cache("subscriptions:*")
                    logger.info(f"Downgraded {len(downgraded)} expired subscriptions")
                
                return downgraded
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in check_and_expire_subscriptions: {e}")
            return []
    
    # Usage tracking and rate limiting
    async def can_make_request(self, user_id: uuid.UUID) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if user can make a request based on subscription limits.
        
        Args:
            user_id: User UUID
            
        Returns:
            Tuple of (can_make_request, limits_info)
        """
        try:
            subscription = await self.get_by_user_id(user_id)
            if not subscription:
                return False, {"error": "No subscription found"}
            
            # Reset daily counter if needed
            today = datetime.now().date()
            if subscription.last_reset_date != today:
                subscription.daily_requests = 0
                subscription.last_reset_date = today
                
                async with self.get_session() as session:
                    await session.merge(subscription)
                    await session.flush()
                
                # Invalidate cache
                await self._invalidate_cache(f"subscriptions:user:{user_id}")
            
            # Check subscription limits
            limits = self._get_tier_limits(subscription.tier)
            daily_limit = limits["daily_requests"]
            
            can_make = (
                daily_limit == -1 or  # Unlimited
                subscription.daily_requests < daily_limit
            )
            
            limits_info = {
                "tier": subscription.tier.value,
                "daily_requests": subscription.daily_requests,
                "daily_limit": daily_limit,
                "remaining": daily_limit - subscription.daily_requests if daily_limit != -1 else -1,
                "expires_at": subscription.expires_at,
            }
            
            return can_make, limits_info
            
        except SQLAlchemyError as e:
            logger.error(f"Database error in can_make_request: {e}")
            return False, {"error": str(e)}
    
    async def increment_request_count(self, user_id: uuid.UUID) -> Optional[UserSubscription]:
        """
        Increment user's daily request count.
        
        Args:
            user_id: User UUID
            
        Returns:
            Updated subscription or None if not found
        """
        try:
            async with self.get_session() as session:
                subscription = await self.get_by_user_id(user_id)
                if not subscription:
                    return None
                
                subscription.daily_requests += 1
                subscription.updated_at = datetime.now()
                
                await session.flush()
                await session.refresh(subscription)
                
                # Invalidate cache
                await self._invalidate_cache(f"subscriptions:user:{user_id}")
                
                return subscription
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in increment_request_count: {e}")
            return None
    
    # Referral system
    async def generate_referral_code(self, user_id: uuid.UUID) -> Optional[str]:
        """
        Generate unique referral code for user.
        
        Args:
            user_id: User UUID
            
        Returns:
            Generated referral code or None if failed
        """
        try:
            async with self.get_session() as session:
                subscription = await self.get_by_user_id(user_id)
                if not subscription:
                    return None
                
                # Generate code based on user_id and timestamp
                raw_data = f"{user_id}_{int(time.time())}"
                code = hashlib.md5(raw_data.encode()).hexdigest()[:8].upper()
                
                # Ensure uniqueness
                existing_stmt = select(UserSubscription).where(
                    UserSubscription.referral_code == code
                )
                existing_result = await session.execute(existing_stmt)
                if existing_result.scalar_one_or_none():
                    # Collision, add timestamp
                    code = f"{code}{int(time.time()) % 1000}"
                
                subscription.referral_code = code
                subscription.updated_at = datetime.now()
                
                await session.flush()
                await session.refresh(subscription)
                
                # Invalidate cache
                await self._invalidate_cache(f"subscriptions:user:{user_id}")
                
                logger.info(f"Generated referral code {code} for user {user_id}")
                return code
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in generate_referral_code: {e}")
            return None
    
    async def apply_referral(
        self,
        user_id: uuid.UUID,
        referral_code: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Apply referral code and give bonuses.
        
        Args:
            user_id: User UUID applying the referral
            referral_code: Referral code to apply
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            async with self.get_session() as session:
                # Get user's subscription
                user_subscription = await self.get_by_user_id(user_id)
                if not user_subscription:
                    return False, "User subscription not found"
                
                # Check if already referred
                if user_subscription.referred_by_user_id:
                    return False, "User already has a referrer"
                
                # Find referrer by code
                referrer_stmt = select(UserSubscription).where(
                    UserSubscription.referral_code == referral_code
                )
                referrer_result = await session.execute(referrer_stmt)
                referrer_subscription = referrer_result.scalar_one_or_none()
                
                if not referrer_subscription:
                    return False, "Invalid referral code"
                
                # Get referrer's user ID
                referrer_user_stmt = select(User).where(User.id == referrer_subscription.user_id)
                referrer_user_result = await session.execute(referrer_user_stmt)
                referrer_user = referrer_user_result.scalar_one_or_none()
                
                if not referrer_user or referrer_user.user_id == user_subscription.user_id:
                    return False, "Cannot refer yourself"
                
                # Apply referral
                user_subscription.referred_by_user_id = referrer_user.user_id
                user_subscription.updated_at = datetime.now()
                
                # Give bonus to referrer (30 days Premium)
                await self.upgrade_subscription(
                    referrer_subscription.user_id,
                    SubscriptionTier.PREMIUM,
                    30,
                    "referral_bonus"
                )
                referrer_subscription.referrals_count += 1
                
                # Give bonus to referred user (7 days Premium)
                await self.upgrade_subscription(
                    user_id,
                    SubscriptionTier.PREMIUM,
                    7,
                    "referral_bonus"
                )
                
                await session.flush()
                
                # Invalidate caches
                await self._invalidate_cache("subscriptions:*")
                
                logger.info(f"Applied referral: {user_id} referred by {referrer_user.user_id}")
                return True, None
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in apply_referral: {e}")
            return False, f"Database error: {e}"
    
    # Subscription analytics
    async def get_subscription_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive subscription statistics.
        
        Returns:
            Dictionary with subscription statistics
        """
        try:
            async with self.get_session() as session:
                # Total subscriptions
                total_subscriptions = await self.count()
                
                # Tier distribution
                tier_stmt = (
                    select(UserSubscription.tier, func.count(UserSubscription.id).label('count'))
                    .group_by(UserSubscription.tier)
                )
                tier_result = await session.execute(tier_stmt)
                tier_distribution = {row.tier.value: row.count for row in tier_result}
                
                # Active subscriptions (non-expired paid)
                active_stmt = (
                    select(func.count(UserSubscription.id))
                    .where(
                        and_(
                            UserSubscription.tier != SubscriptionTier.FREE,
                            or_(
                                UserSubscription.expires_at.is_(None),
                                UserSubscription.expires_at > datetime.now()
                            )
                        )
                    )
                )
                active_result = await session.execute(active_stmt)
                active_subscriptions = active_result.scalar() or 0
                
                # Referral statistics
                referral_stmt = (
                    select(func.count(UserSubscription.id))
                    .where(UserSubscription.referred_by_user_id.is_not(None))
                )
                referral_result = await session.execute(referral_stmt)
                referred_users = referral_result.scalar() or 0
                
                # Top referrers
                top_referrers_stmt = (
                    select(
                        UserSubscription.referrals_count,
                        User.user_id,
                        User.faceit_nickname
                    )
                    .join(User)
                    .where(UserSubscription.referrals_count > 0)
                    .order_by(desc(UserSubscription.referrals_count))
                    .limit(10)
                )
                top_referrers_result = await session.execute(top_referrers_stmt)
                top_referrers = [
                    {
                        "user_id": row.user_id,
                        "nickname": row.faceit_nickname,
                        "referrals": row.referrals_count
                    }
                    for row in top_referrers_result
                ]
                
                # Daily usage statistics
                usage_stmt = (
                    select(func.sum(UserSubscription.daily_requests))
                    .where(UserSubscription.last_reset_date == datetime.now().date())
                )
                usage_result = await session.execute(usage_stmt)
                daily_requests = usage_result.scalar() or 0
                
                return {
                    "total_subscriptions": total_subscriptions,
                    "tier_distribution": tier_distribution,
                    "active_paid_subscriptions": active_subscriptions,
                    "referred_users": referred_users,
                    "referral_rate": round((referred_users / total_subscriptions * 100) if total_subscriptions > 0 else 0, 2),
                    "daily_requests_today": daily_requests,
                    "top_referrers": top_referrers,
                    "conversion_rate": round((active_subscriptions / total_subscriptions * 100) if total_subscriptions > 0 else 0, 2),
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_subscription_stats: {e}")
            return {"error": str(e)}
    
    async def get_expiring_subscriptions(self, days_ahead: int = 7) -> List[UserSubscription]:
        """
        Get subscriptions expiring within specified days.
        
        Args:
            days_ahead: Number of days to look ahead
            
        Returns:
            List of expiring subscriptions
        """
        try:
            future_date = datetime.now() + timedelta(days=days_ahead)
            
            return await self.get_all(
                filters={
                    'expires_at': {'lte': future_date},
                    'tier': [SubscriptionTier.PREMIUM, SubscriptionTier.PRO]
                },
                order_by='expires_at'
            )
            
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_expiring_subscriptions: {e}")
            return []
    
    # Helper methods
    def _get_tier_limits(self, tier: SubscriptionTier) -> Dict[str, Any]:
        """
        Get limits for subscription tier.
        
        Args:
            tier: Subscription tier
            
        Returns:
            Dictionary with tier limits
        """
        limits = {
            SubscriptionTier.FREE: {
                "daily_requests": 10,
                "matches_history": 20,
                "advanced_analytics": False,
                "notifications": True,
                "api_access": False
            },
            SubscriptionTier.PREMIUM: {
                "daily_requests": 100,
                "matches_history": 50,
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
        
        return limits.get(tier, limits[SubscriptionTier.FREE])


class PaymentRepository(BaseRepository[Payment, PaymentCreateData, Dict]):
    """Repository for Payment entity management."""
    
    def __init__(self):
        """Initialize payment repository with Redis cache."""
        super().__init__(Payment, stats_cache)
    
    # Payment operations
    async def create_payment(
        self,
        user_id: uuid.UUID,
        amount: int,
        subscription_tier: SubscriptionTier,
        subscription_duration: str,
        duration_days: int,
        description: str,
        payment_payload: Optional[str] = None
    ) -> Payment:
        """
        Create new payment record.
        
        Args:
            user_id: User UUID
            amount: Payment amount in Telegram Stars
            subscription_tier: Target subscription tier
            subscription_duration: Duration type (monthly/yearly)
            duration_days: Duration in days
            description: Payment description
            payment_payload: Optional payment payload
            
        Returns:
            Created payment record
        """
        try:
            async with self.get_session() as session:
                payment = Payment(
                    user_id=user_id,
                    amount=amount,
                    subscription_tier=subscription_tier,
                    subscription_duration=subscription_duration,
                    duration_days=duration_days,
                    description=description,
                    payment_payload=payment_payload,
                    status=PaymentStatus.PENDING,
                    created_at=datetime.now()
                )
                
                session.add(payment)
                await session.flush()
                await session.refresh(payment)
                
                logger.info(f"Created payment record {payment.id} for user {user_id}")
                return payment
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in create_payment: {e}")
            raise DatabaseOperationError(f"Failed to create payment: {e}")
    
    async def complete_payment(
        self,
        payment_id: uuid.UUID,
        telegram_payment_charge_id: str,
        provider_payment_charge_id: Optional[str] = None
    ) -> Optional[Payment]:
        """
        Mark payment as completed.
        
        Args:
            payment_id: Payment UUID
            telegram_payment_charge_id: Telegram charge ID
            provider_payment_charge_id: Provider charge ID
            
        Returns:
            Updated payment or None if not found
        """
        try:
            async with self.get_session() as session:
                payment = await self.get_by_id(payment_id)
                if not payment:
                    return None
                
                payment.status = PaymentStatus.COMPLETED
                payment.telegram_payment_charge_id = telegram_payment_charge_id
                payment.provider_payment_charge_id = provider_payment_charge_id
                payment.processed_at = datetime.now()
                payment.updated_at = datetime.now()
                
                await session.flush()
                await session.refresh(payment)
                
                # Invalidate cache
                await self._invalidate_cache("payments:*")
                
                logger.info(f"Completed payment {payment_id}")
                return payment
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in complete_payment: {e}")
            raise DatabaseOperationError(f"Failed to complete payment: {e}")
    
    async def fail_payment(
        self,
        payment_id: uuid.UUID,
        error_message: str
    ) -> Optional[Payment]:
        """
        Mark payment as failed.
        
        Args:
            payment_id: Payment UUID
            error_message: Error description
            
        Returns:
            Updated payment or None if not found
        """
        try:
            async with self.get_session() as session:
                payment = await self.get_by_id(payment_id)
                if not payment:
                    return None
                
                payment.status = PaymentStatus.FAILED
                payment.error_message = error_message
                payment.processed_at = datetime.now()
                payment.updated_at = datetime.now()
                
                await session.flush()
                await session.refresh(payment)
                
                # Invalidate cache
                await self._invalidate_cache("payments:*")
                
                logger.info(f"Failed payment {payment_id}: {error_message}")
                return payment
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in fail_payment: {e}")
            raise DatabaseOperationError(f"Failed to update payment: {e}")
    
    # Payment queries
    async def get_user_payments(
        self,
        user_id: uuid.UUID,
        limit: int = 20,
        status: Optional[PaymentStatus] = None
    ) -> List[Payment]:
        """
        Get user's payment history.
        
        Args:
            user_id: User UUID
            limit: Maximum number of payments
            status: Optional status filter
            
        Returns:
            List of user payments
        """
        filters = {'user_id': user_id}
        if status:
            filters['status'] = status
        
        return await self.get_all(
            limit=limit,
            filters=filters,
            order_by='created_at',
            order_desc=True
        )
    
    async def get_revenue_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get revenue statistics.
        
        Args:
            start_date: Start date for analysis
            end_date: End date for analysis
            
        Returns:
            Revenue statistics
        """
        try:
            async with self.get_session() as session:
                stmt = (
                    select(
                        func.sum(Payment.amount).label('total_revenue'),
                        func.count(Payment.id).label('total_payments'),
                        Payment.subscription_tier,
                        Payment.subscription_duration
                    )
                    .where(Payment.status == PaymentStatus.COMPLETED)
                )
                
                if start_date:
                    stmt = stmt.where(Payment.created_at >= start_date)
                if end_date:
                    stmt = stmt.where(Payment.created_at <= end_date)
                
                stmt = stmt.group_by(Payment.subscription_tier, Payment.subscription_duration)
                
                result = await session.execute(stmt)
                
                revenue_breakdown = {}
                total_revenue = 0
                total_payments = 0
                
                for row in result:
                    key = f"{row.subscription_tier.value}_{row.subscription_duration}"
                    revenue_breakdown[key] = {
                        "revenue": row.total_revenue or 0,
                        "payments": row.total_payments or 0
                    }
                    total_revenue += row.total_revenue or 0
                    total_payments += row.total_payments or 0
                
                return {
                    "total_revenue": total_revenue,
                    "total_payments": total_payments,
                    "average_payment": round(total_revenue / total_payments, 2) if total_payments > 0 else 0,
                    "revenue_breakdown": revenue_breakdown,
                    "period": {
                        "start": start_date.isoformat() if start_date else None,
                        "end": end_date.isoformat() if end_date else None
                    }
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_revenue_stats: {e}")
            return {"error": str(e)}