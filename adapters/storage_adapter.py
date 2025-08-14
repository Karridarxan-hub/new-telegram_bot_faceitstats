"""
Storage Adapter for dual JSON/PostgreSQL support.

Provides a unified interface that can route operations between
legacy JSON storage and new PostgreSQL ORM services based on
configuration settings.
"""

import logging
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
from enum import Enum

from utils.storage import storage as json_storage, UserData, SubscriptionTier
from services.user import UserService
from services.subscription import SubscriptionService
from config.settings import settings

logger = logging.getLogger(__name__)


class StorageBackend(str, Enum):
    """Storage backend options."""
    JSON = "json"
    POSTGRESQL = "postgresql"
    DUAL = "dual"  # Both backends for migration


class StorageAdapter:
    """
    Unified storage adapter supporting both JSON and PostgreSQL backends.
    
    Provides seamless switching between storage backends with data
    consistency validation and migration support.
    """
    
    def __init__(
        self,
        backend: StorageBackend = None,
        user_service: Optional[UserService] = None,
        subscription_service: Optional[SubscriptionService] = None
    ):
        """
        Initialize storage adapter.
        
        Args:
            backend: Storage backend to use (defaults to settings)
            user_service: PostgreSQL user service instance
            subscription_service: PostgreSQL subscription service instance
        """
        self.backend = backend or getattr(settings, 'storage_backend', StorageBackend.JSON)
        self.user_service = user_service
        self.subscription_service = subscription_service
        
        # Track dual mode state
        self._dual_mode_active = self.backend == StorageBackend.DUAL
        
        logger.info(f"StorageAdapter initialized with backend: {self.backend}")
    
    async def get_user(self, user_id: int) -> Optional[UserData]:
        """
        Get user by Telegram ID from appropriate backend.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            UserData instance or None if not found
        """
        try:
            if self.backend == StorageBackend.JSON:
                return await self._get_user_json(user_id)
            
            elif self.backend == StorageBackend.POSTGRESQL:
                return await self._get_user_postgresql(user_id)
            
            elif self.backend == StorageBackend.DUAL:
                # Try PostgreSQL first, fallback to JSON
                pg_user = await self._get_user_postgresql(user_id)
                if pg_user:
                    return pg_user
                
                json_user = await self._get_user_json(user_id)
                if json_user:
                    # Auto-migrate user from JSON to PostgreSQL
                    logger.info(f"Auto-migrating user {user_id} from JSON to PostgreSQL")
                    await self._migrate_user_to_postgresql(json_user)
                    return json_user
                
                return None
        
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            # Fallback to JSON if PostgreSQL fails
            if self.backend != StorageBackend.JSON:
                try:
                    return await self._get_user_json(user_id)
                except Exception as fallback_error:
                    logger.error(f"Fallback error: {fallback_error}")
            return None
    
    async def save_user(self, user_data: UserData) -> bool:
        """
        Save user to appropriate backend(s).
        
        Args:
            user_data: UserData instance to save
            
        Returns:
            Success status
        """
        try:
            success = True
            
            if self.backend in [StorageBackend.JSON, StorageBackend.DUAL]:
                await json_storage.save_user(user_data)
                logger.debug(f"Saved user {user_data.user_id} to JSON")
            
            if self.backend in [StorageBackend.POSTGRESQL, StorageBackend.DUAL]:
                pg_success = await self._save_user_postgresql(user_data)
                if not pg_success:
                    success = False
                    logger.warning(f"Failed to save user {user_data.user_id} to PostgreSQL")
                else:
                    logger.debug(f"Saved user {user_data.user_id} to PostgreSQL")
            
            return success
        
        except Exception as e:
            logger.error(f"Error saving user {user_data.user_id}: {e}")
            return False
    
    async def get_all_users(self) -> List[UserData]:
        """
        Get all users from appropriate backend.
        
        Returns:
            List of UserData instances
        """
        try:
            if self.backend == StorageBackend.JSON:
                return await json_storage.get_all_users()
            
            elif self.backend == StorageBackend.POSTGRESQL:
                return await self._get_all_users_postgresql()
            
            elif self.backend == StorageBackend.DUAL:
                # Get users from both backends and merge
                pg_users = await self._get_all_users_postgresql()
                json_users = await json_storage.get_all_users()
                
                # Merge users, preferring PostgreSQL data
                user_map = {}
                
                # Add JSON users first
                for user in json_users:
                    user_map[user.user_id] = user
                
                # Override with PostgreSQL users
                for user in pg_users:
                    user_map[user.user_id] = user
                
                return list(user_map.values())
        
        except Exception as e:
            logger.error(f"Error getting all users: {e}")
            # Fallback to JSON
            try:
                return await json_storage.get_all_users()
            except Exception as fallback_error:
                logger.error(f"Fallback error: {fallback_error}")
                return []
    
    async def update_last_checked_match(self, user_id: int, match_id: str) -> bool:
        """
        Update last checked match for user.
        
        Args:
            user_id: Telegram user ID
            match_id: Match ID
            
        Returns:
            Success status
        """
        try:
            success = True
            
            if self.backend in [StorageBackend.JSON, StorageBackend.DUAL]:
                await json_storage.update_last_checked_match(user_id, match_id)
            
            if self.backend in [StorageBackend.POSTGRESQL, StorageBackend.DUAL]:
                if self.user_service:
                    result = await self.user_service.update_activity(
                        user_id, 
                        "match_check",
                        {"match_id": match_id}
                    )
                    if not result.success:
                        success = False
                        logger.warning(f"Failed to update match check for user {user_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Error updating last checked match for user {user_id}: {e}")
            return False
    
    async def can_make_request(self, user_id: int) -> bool:
        """
        Check if user can make a request based on subscription limits.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Whether user can make request
        """
        try:
            if self.backend == StorageBackend.JSON:
                return await json_storage.can_make_request(user_id)
            
            elif self.backend in [StorageBackend.POSTGRESQL, StorageBackend.DUAL]:
                if self.subscription_service:
                    result = await self.subscription_service.can_make_request(user_id)
                    return result.data if result.success else False
            
            # Fallback to JSON
            return await json_storage.can_make_request(user_id)
        
        except Exception as e:
            logger.error(f"Error checking request permission for user {user_id}: {e}")
            # Default to allowing request if check fails
            return True
    
    async def increment_request_count(self, user_id: int) -> bool:
        """
        Increment user's daily request count.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Success status
        """
        try:
            success = True
            
            if self.backend in [StorageBackend.JSON, StorageBackend.DUAL]:
                await json_storage.increment_request_count(user_id)
            
            if self.backend in [StorageBackend.POSTGRESQL, StorageBackend.DUAL]:
                if self.subscription_service:
                    result = await self.subscription_service.increment_usage(user_id)
                    if not result.success:
                        success = False
                        logger.warning(f"Failed to increment request count for user {user_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Error incrementing request count for user {user_id}: {e}")
            return False
    
    async def upgrade_subscription(
        self,
        user_id: int,
        tier: SubscriptionTier,
        duration_days: int = 30,
        payment_method: str = "telegram_stars"
    ) -> bool:
        """
        Upgrade user subscription.
        
        Args:
            user_id: Telegram user ID
            tier: Subscription tier
            duration_days: Duration in days
            payment_method: Payment method
            
        Returns:
            Success status
        """
        try:
            success = True
            
            if self.backend in [StorageBackend.JSON, StorageBackend.DUAL]:
                json_success = await json_storage.upgrade_subscription(
                    user_id, tier, duration_days, payment_method
                )
                if not json_success:
                    success = False
            
            if self.backend in [StorageBackend.POSTGRESQL, StorageBackend.DUAL]:
                if self.subscription_service:
                    result = await self.subscription_service.upgrade_subscription(
                        user_id, tier, duration_days
                    )
                    if not result.success:
                        success = False
                        logger.warning(f"Failed to upgrade subscription for user {user_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Error upgrading subscription for user {user_id}: {e}")
            return False
    
    async def apply_referral(self, user_id: int, referral_code: str) -> bool:
        """
        Apply referral code.
        
        Args:
            user_id: Telegram user ID
            referral_code: Referral code
            
        Returns:
            Success status
        """
        try:
            success = True
            
            if self.backend in [StorageBackend.JSON, StorageBackend.DUAL]:
                json_success = await json_storage.apply_referral(user_id, referral_code)
                if not json_success:
                    success = False
            
            if self.backend in [StorageBackend.POSTGRESQL, StorageBackend.DUAL]:
                if self.subscription_service:
                    result = await self.subscription_service.apply_referral(user_id, referral_code)
                    if not result.success:
                        success = False
                        logger.warning(f"Failed to apply referral for user {user_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Error applying referral for user {user_id}: {e}")
            return False
    
    async def generate_referral_code(self, user_id: int) -> Optional[str]:
        """
        Generate referral code for user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Generated referral code or None
        """
        try:
            if self.backend == StorageBackend.JSON:
                return await json_storage.generate_referral_code(user_id)
            
            elif self.backend in [StorageBackend.POSTGRESQL, StorageBackend.DUAL]:
                if self.subscription_service:
                    result = await self.subscription_service.generate_referral_code(user_id)
                    if result.success:
                        return result.data
            
            # Fallback to JSON
            return await json_storage.generate_referral_code(user_id)
        
        except Exception as e:
            logger.error(f"Error generating referral code for user {user_id}: {e}")
            return None
    
    # Backend-specific helper methods
    async def _get_user_json(self, user_id: int) -> Optional[UserData]:
        """Get user from JSON storage."""
        return await json_storage.get_user(user_id)
    
    async def _get_user_postgresql(self, user_id: int) -> Optional[UserData]:
        """Get user from PostgreSQL storage."""
        if not self.user_service:
            return None
        
        result = await self.user_service.get_user_profile(
            user_id, include_subscription=True, include_stats=False
        )
        
        if not result.success:
            return None
        
        profile = result.data
        
        # Convert PostgreSQL user profile to UserData
        return UserData(
            user_id=profile["user_id"],
            faceit_player_id=profile.get("faceit_player_id"),
            faceit_nickname=profile.get("faceit_nickname"),
            waiting_for_nickname=profile.get("waiting_for_nickname", False),
            language=profile.get("language", "ru"),
            notifications_enabled=profile.get("notifications_enabled", True),
            created_at=profile.get("created_at"),
            last_active_at=profile.get("last_active_at"),
            total_requests=profile.get("total_requests", 0)
            # Note: subscription data would be mapped separately
        )
    
    async def _save_user_postgresql(self, user_data: UserData) -> bool:
        """Save user to PostgreSQL storage."""
        if not self.user_service:
            return False
        
        try:
            # Check if user exists
            existing_profile = await self.user_service.get_user_profile(user_data.user_id)
            
            if existing_profile.success:
                # Update existing user
                preferences = {
                    "language": user_data.language,
                    "notifications_enabled": user_data.notifications_enabled
                }
                result = await self.user_service.update_user_preferences(
                    user_data.user_id, preferences
                )
                
                # Update FACEIT info if needed
                if user_data.faceit_player_id and user_data.faceit_nickname:
                    await self.user_service.link_faceit_account(
                        user_data.user_id, user_data.faceit_nickname
                    )
                
                return result.success
            else:
                # Create new user
                result = await self.user_service.create_user(
                    user_data.user_id,
                    user_data.faceit_nickname,
                    user_data.language
                )
                return result.success
        
        except Exception as e:
            logger.error(f"Error saving user to PostgreSQL: {e}")
            return False
    
    async def _get_all_users_postgresql(self) -> List[UserData]:
        """Get all users from PostgreSQL storage."""
        if not self.user_service:
            return []
        
        try:
            result = await self.user_service.search_users(faceit_only=True, limit=1000)
            if not result.success:
                return []
            
            users = []
            for user_dict in result.data:
                user_data = UserData(
                    user_id=user_dict["telegram_user_id"],
                    faceit_nickname=user_dict.get("faceit_nickname"),
                    language=user_dict.get("language", "ru"),
                    created_at=user_dict.get("created_at"),
                    last_active_at=user_dict.get("last_active_at"),
                    total_requests=user_dict.get("total_requests", 0)
                )
                users.append(user_data)
            
            return users
        
        except Exception as e:
            logger.error(f"Error getting all users from PostgreSQL: {e}")
            return []
    
    async def _migrate_user_to_postgresql(self, user_data: UserData) -> bool:
        """Migrate user from JSON to PostgreSQL."""
        try:
            return await self._save_user_postgresql(user_data)
        except Exception as e:
            logger.error(f"Error migrating user {user_data.user_id} to PostgreSQL: {e}")
            return False
    
    # Health and diagnostics
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on storage backends.
        
        Returns:
            Health status information
        """
        health = {
            "backend": self.backend.value,
            "json_status": "unknown",
            "postgresql_status": "unknown",
            "timestamp": datetime.now().isoformat()
        }
        
        # Check JSON storage
        try:
            test_user = await json_storage.get_user(999999999)  # Non-existent user
            health["json_status"] = "healthy"
        except Exception as e:
            health["json_status"] = f"error: {e}"
        
        # Check PostgreSQL storage
        if self.user_service:
            try:
                result = await self.user_service.health_check()
                health["postgresql_status"] = "healthy" if result.success else f"error: {result.error}"
            except Exception as e:
                health["postgresql_status"] = f"error: {e}"
        
        return health
    
    def get_backend_info(self) -> Dict[str, Any]:
        """
        Get information about current backend configuration.
        
        Returns:
            Backend configuration information
        """
        return {
            "current_backend": self.backend.value,
            "dual_mode_active": self._dual_mode_active,
            "user_service_available": self.user_service is not None,
            "subscription_service_available": self.subscription_service is not None,
            "json_storage_path": getattr(json_storage, 'file_path', None)
        }