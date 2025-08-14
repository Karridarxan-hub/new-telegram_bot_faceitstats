"""Data storage utilities."""

import json
import asyncio
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timedelta
from enum import Enum
from pydantic import BaseModel, Field

from config.settings import settings

logger = logging.getLogger(__name__)


class SubscriptionTier(str, Enum):
    """Subscription tier enumeration."""
    FREE = "free"
    PREMIUM = "premium"
    PRO = "pro"


class UserSubscription(BaseModel):
    """User subscription model."""
    tier: SubscriptionTier = SubscriptionTier.FREE
    expires_at: Optional[datetime] = None
    auto_renew: bool = False
    payment_method: Optional[str] = None
    
    # Usage tracking
    daily_requests: int = 0
    last_reset_date: Optional[datetime] = None
    
    # Referral system
    referred_by: Optional[int] = None
    referral_code: Optional[str] = None
    referrals_count: int = 0


class UserData(BaseModel):
    """User data model."""
    user_id: int
    faceit_player_id: Optional[str] = None
    faceit_nickname: Optional[str] = None
    last_checked_match_id: Optional[str] = None
    waiting_for_nickname: bool = False
    
    # Subscription data
    subscription: UserSubscription = Field(default_factory=UserSubscription)
    
    # User preferences
    language: str = "ru"
    notifications_enabled: bool = True
    
    # Analytics
    created_at: datetime = Field(default_factory=datetime.now)
    last_active_at: Optional[datetime] = None
    total_requests: int = 0
    
    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat() if dt else None
        }


class DataStorage:
    """JSON file storage for user data."""
    
    def __init__(self, file_path: Optional[str] = None):
        self.file_path = Path(file_path or settings.data_file_path)
        self._lock = asyncio.Lock()
    
    async def _read_data(self) -> Dict[str, Any]:
        """Read data from file."""
        try:
            if self.file_path.exists():
                content = await asyncio.to_thread(self.file_path.read_text, encoding="utf-8")
                return json.loads(content)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read data file: {e}")
        
        return {"users": [], "analytics": {"total_users": 0, "daily_stats": {}}}
    
    async def _write_data(self, data: Dict[str, Any]) -> None:
        """Write data to file."""
        try:
            json_content = json.dumps(data, indent=2, ensure_ascii=False)
            await asyncio.to_thread(
                self.file_path.write_text, 
                json_content, 
                encoding="utf-8"
            )
        except OSError as e:
            logger.error(f"Failed to write data file: {e}")
            raise
    
    async def get_user(self, user_id: int) -> Optional[UserData]:
        """Get user by ID."""
        async with self._lock:
            data = await self._read_data()
            users = data.get("users", [])
            
            for user_dict in users:
                if user_dict.get("user_id") == user_id:
                    try:
                        # Handle datetime fields
                        if "subscription" in user_dict:
                            sub = user_dict["subscription"]
                            if "expires_at" in sub and sub["expires_at"]:
                                sub["expires_at"] = datetime.fromisoformat(sub["expires_at"])
                            if "last_reset_date" in sub and sub["last_reset_date"]:
                                sub["last_reset_date"] = datetime.fromisoformat(sub["last_reset_date"])
                        
                        if "created_at" in user_dict and user_dict["created_at"]:
                            user_dict["created_at"] = datetime.fromisoformat(user_dict["created_at"])
                        if "last_active_at" in user_dict and user_dict["last_active_at"]:
                            user_dict["last_active_at"] = datetime.fromisoformat(user_dict["last_active_at"])
                            
                        return UserData(**user_dict)
                    except Exception as e:
                        logger.error(f"Failed to parse user data: {e}")
                        return None
            
            return None
    
    async def save_user(self, user_data: UserData) -> None:
        """Save or update user data."""
        async with self._lock:
            data = await self._read_data()
            users = data.get("users", [])
            
            # Find existing user
            user_index = None
            for i, user_dict in enumerate(users):
                if user_dict.get("user_id") == user_data.user_id:
                    user_index = i
                    break
            
            # Update or add user
            user_dict = user_data.dict()
            if user_index is not None:
                users[user_index] = user_dict
            else:
                users.append(user_dict)
            
            data["users"] = users
            await self._write_data(data)
            
            logger.info(f"Saved user data for user {user_data.user_id}")
    
    async def get_all_users(self) -> List[UserData]:
        """Get all users with FACEIT accounts."""
        async with self._lock:
            data = await self._read_data()
            users = data.get("users", [])
            
            result = []
            for user_dict in users:
                try:
                    user = UserData(**user_dict)
                    if user.faceit_player_id:  # Only users with FACEIT accounts
                        result.append(user)
                except Exception as e:
                    logger.error(f"Failed to parse user data: {e}")
            
            return result
    
    async def update_last_checked_match(
        self, 
        user_id: int, 
        match_id: str
    ) -> None:
        """Update last checked match ID for user."""
        user = await self.get_user(user_id)
        if user:
            user.last_checked_match_id = match_id
            await self.save_user(user)
            logger.info(f"Updated last checked match for user {user_id}: {match_id}")
    
    async def can_make_request(self, user_id: int) -> bool:
        """Check if user can make a request based on their subscription limits."""
        user = await self.get_user(user_id)
        if not user:
            return False
        
        # Reset daily counter if needed
        today = datetime.now().date()
        if (not user.subscription.last_reset_date or 
            user.subscription.last_reset_date.date() != today):
            user.subscription.daily_requests = 0
            user.subscription.last_reset_date = datetime.now()
            await self.save_user(user)
        
        # Check subscription status
        if user.subscription.tier == SubscriptionTier.FREE:
            return user.subscription.daily_requests < 10
        elif user.subscription.tier == SubscriptionTier.PREMIUM:
            return user.subscription.daily_requests < 1000
        else:  # PRO
            return True  # Unlimited
    
    async def increment_request_count(self, user_id: int) -> None:
        """Increment user's daily request count."""
        user = await self.get_user(user_id)
        if user:
            user.subscription.daily_requests += 1
            user.total_requests += 1
            user.last_active_at = datetime.now()
            await self.save_user(user)
    
    async def upgrade_subscription(
        self, 
        user_id: int, 
        tier: SubscriptionTier,
        duration_days: int = 30,
        payment_method: str = "telegram_stars"
    ) -> bool:
        """Upgrade user subscription."""
        user = await self.get_user(user_id)
        if not user:
            return False
        
        # Calculate expiration date
        if user.subscription.expires_at and user.subscription.expires_at > datetime.now():
            # Extend existing subscription
            expires_at = user.subscription.expires_at + timedelta(days=duration_days)
        else:
            # New subscription
            expires_at = datetime.now() + timedelta(days=duration_days)
        
        user.subscription.tier = tier
        user.subscription.expires_at = expires_at
        user.subscription.payment_method = payment_method
        user.subscription.auto_renew = True
        
        await self.save_user(user)
        logger.info(f"Upgraded user {user_id} to {tier} until {expires_at}")
        return True
    
    async def check_expired_subscriptions(self) -> List[UserData]:
        """Check for expired subscriptions and downgrade users."""
        expired_users = []
        all_users = await self.get_all_users()
        
        for user in all_users:
            if (user.subscription.tier != SubscriptionTier.FREE and
                user.subscription.expires_at and
                user.subscription.expires_at < datetime.now()):
                
                user.subscription.tier = SubscriptionTier.FREE
                user.subscription.expires_at = None
                user.subscription.auto_renew = False
                
                await self.save_user(user)
                expired_users.append(user)
                logger.info(f"Downgraded expired subscription for user {user.user_id}")
        
        return expired_users
    
    async def generate_referral_code(self, user_id: int) -> Optional[str]:
        """Generate unique referral code for user."""
        import hashlib
        import time
        
        user = await self.get_user(user_id)
        if not user:
            return None
        
        # Generate code based on user_id and timestamp
        raw_data = f"{user_id}_{int(time.time())}"
        code = hashlib.md5(raw_data.encode()).hexdigest()[:8].upper()
        
        user.subscription.referral_code = code
        await self.save_user(user)
        
        return code
    
    async def apply_referral(self, user_id: int, referral_code: str) -> bool:
        """Apply referral code and give bonus."""
        user = await self.get_user(user_id)
        if not user or user.subscription.referred_by:
            return False  # Already referred or user not found
        
        # Find referrer by code
        all_users = await self.get_all_users()
        referrer = None
        
        for potential_referrer in all_users:
            if potential_referrer.subscription.referral_code == referral_code:
                referrer = potential_referrer
                break
        
        if not referrer or referrer.user_id == user_id:
            return False  # Invalid code or self-referral
        
        # Apply referral
        user.subscription.referred_by = referrer.user_id
        
        # Give bonus to referrer (30 days premium)
        await self.upgrade_subscription(referrer.user_id, SubscriptionTier.PREMIUM, 30, "referral_bonus")
        referrer.subscription.referrals_count += 1
        
        # Give bonus to referred user (7 days premium)
        await self.upgrade_subscription(user_id, SubscriptionTier.PREMIUM, 7, "referral_bonus")
        
        await self.save_user(user)
        await self.save_user(referrer)
        
        logger.info(f"Applied referral: {user_id} referred by {referrer.user_id}")
        return True
    
    async def get_subscription_stats(self) -> Dict[str, Any]:
        """Get subscription statistics."""
        all_users = await self.get_all_users()
        
        stats = {
            "total_users": len(all_users),
            "free_users": 0,
            "premium_users": 0,
            "pro_users": 0,
            "active_users": 0,
            "daily_requests": 0
        }
        
        today = datetime.now().date()
        
        for user in all_users:
            if user.subscription.tier == SubscriptionTier.FREE:
                stats["free_users"] += 1
            elif user.subscription.tier == SubscriptionTier.PREMIUM:
                stats["premium_users"] += 1
            elif user.subscription.tier == SubscriptionTier.PRO:
                stats["pro_users"] += 1
            
            if user.last_active_at and user.last_active_at.date() == today:
                stats["active_users"] += 1
            
            stats["daily_requests"] += user.subscription.daily_requests
        
        return stats


# Global storage instance
storage = DataStorage()