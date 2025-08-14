"""
User Service implementation with FACEIT integration.

Provides comprehensive user management functionality:
- User registration and profile management
- FACEIT account linking and verification
- Activity tracking and engagement metrics
- User preferences and settings
- Integration with subscription system
- Multi-language support
- Privacy and security features
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import re
import uuid

from database.repositories.user import UserRepository
from database.repositories.subscription import SubscriptionRepository
from database.models import User, UserSubscription, SubscriptionTier
from faceit.api import FaceitAPI, FaceitAPIError
from faceit.models import FaceitPlayer
from utils.redis_cache import player_cache, stats_cache
from utils.storage import storage as legacy_storage  # Legacy JSON storage
from .base import (
    BaseService, ServiceResult, ServiceError, ValidationError,
    BusinessRuleError, EventType
)

logger = logging.getLogger(__name__)


class UserService(BaseService):
    """
    Service for user management and FACEIT integration.
    
    Handles:
    - User registration and onboarding
    - FACEIT account linking and validation
    - Profile updates and preferences
    - Activity tracking and analytics
    - Integration with subscription system
    - Legacy data migration support
    """
    
    def __init__(
        self,
        user_repository: UserRepository,
        subscription_repository: SubscriptionRepository,
        faceit_api: FaceitAPI,
        cache=None
    ):
        super().__init__(cache or player_cache)
        self.user_repo = user_repository
        self.subscription_repo = subscription_repository
        self.faceit_api = faceit_api
        
        # Register repositories for base service functionality
        self.register_repository("user", user_repository)
        self.register_repository("subscription", subscription_repository)
    
    # Core user operations
    async def create_user(
        self,
        telegram_user_id: int,
        faceit_nickname: Optional[str] = None,
        language: str = "ru",
        referral_code: Optional[str] = None
    ) -> ServiceResult[User]:
        """
        Create new user with optional FACEIT account linking.
        
        Args:
            telegram_user_id: Telegram user ID
            faceit_nickname: Optional FACEIT nickname to link
            language: User language preference
            referral_code: Optional referral code to apply
            
        Returns:
            ServiceResult containing created user or error
        """
        try:
            # Validate input
            self.validate_required_fields(
                {"telegram_user_id": telegram_user_id, "language": language},
                ["telegram_user_id", "language"]
            )
            
            self.validate_field_constraints(
                {
                    "telegram_user_id": telegram_user_id,
                    "language": language,
                    "faceit_nickname": faceit_nickname,
                    "referral_code": referral_code
                },
                {
                    "telegram_user_id": {"type": int, "min_value": 1},
                    "language": {"type": str, "max_length": 10},
                    "faceit_nickname": {"type": str, "max_length": 50},
                    "referral_code": {"type": str, "max_length": 20}
                }
            )
            
            # Check if user already exists
            existing_user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if existing_user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} already exists",
                    "USER_ALREADY_EXISTS",
                    {"existing_user_id": existing_user.id}
                )
            
            # Validate and fetch FACEIT player if nickname provided
            faceit_player_id = None
            validated_nickname = None
            
            if faceit_nickname:
                player_result = await self._validate_faceit_player(faceit_nickname)
                if not player_result.success:
                    return ServiceResult.error_result(player_result.error)
                
                faceit_player = player_result.data
                faceit_player_id = faceit_player.player_id
                validated_nickname = faceit_player.nickname
            
            # Perform user creation with transaction
            result, processing_time = await self.measure_performance(
                "create_user",
                self._create_user_transaction,
                telegram_user_id,
                faceit_player_id,
                validated_nickname,
                language,
                referral_code
            )
            
            # Publish user created event
            await self.publish_event(
                EventType.USER_CREATED,
                result.id,
                {
                    "telegram_user_id": telegram_user_id,
                    "faceit_linked": faceit_player_id is not None,
                    "language": language,
                    "referral_applied": referral_code is not None
                },
                {"processing_time_ms": processing_time}
            )
            
            return ServiceResult.success_result(
                result,
                metadata={
                    "faceit_linked": faceit_player_id is not None,
                    "referral_applied": referral_code is not None
                },
                processing_time_ms=processing_time
            )
            
        except ValidationError as e:
            return ServiceResult.error_result(e)
        except BusinessRuleError as e:
            return ServiceResult.error_result(e)
        except Exception as e:
            logger.error(f"Unexpected error in create_user: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to create user: {e}", "USER_CREATION_ERROR")
            )
    
    async def _create_user_transaction(
        self,
        telegram_user_id: int,
        faceit_player_id: Optional[str],
        faceit_nickname: Optional[str],
        language: str,
        referral_code: Optional[str]
    ) -> User:
        """Create user within database transaction."""
        async with self.get_session() as session:
            # Create user
            user = await self.user_repo.create_user(
                user_id=telegram_user_id,
                faceit_player_id=faceit_player_id,
                faceit_nickname=faceit_nickname,
                language=language
            )
            
            # Create default subscription
            await self.subscription_repo.create_default_subscription(user.id)
            
            # Apply referral if provided
            if referral_code:
                try:
                    success, error_msg = await self.subscription_repo.apply_referral(
                        user.id, referral_code
                    )
                    if not success:
                        logger.warning(f"Failed to apply referral {referral_code}: {error_msg}")
                except Exception as e:
                    logger.warning(f"Error applying referral {referral_code}: {e}")
            
            # Migrate legacy data if exists
            await self._migrate_legacy_user_data(telegram_user_id, user.id)
            
            return user
    
    async def link_faceit_account(
        self,
        telegram_user_id: int,
        faceit_nickname: str
    ) -> ServiceResult[User]:
        """
        Link FACEIT account to existing user.
        
        Args:
            telegram_user_id: Telegram user ID
            faceit_nickname: FACEIT nickname to link
            
        Returns:
            ServiceResult with updated user
        """
        try:
            # Validate FACEIT player
            player_result = await self._validate_faceit_player(faceit_nickname)
            if not player_result.success:
                return ServiceResult.error_result(player_result.error)
            
            faceit_player = player_result.data
            
            # Check if FACEIT account is already linked to another user
            existing_user = await self.user_repo.get_by_faceit_id(faceit_player.player_id)
            if existing_user and existing_user.user_id != telegram_user_id:
                return ServiceResult.business_rule_error(
                    f"FACEIT account '{faceit_nickname}' is already linked to another user",
                    "FACEIT_ALREADY_LINKED",
                    {"linked_to_user": existing_user.user_id}
                )
            
            # Link account
            result, processing_time = await self.measure_performance(
                "link_faceit_account",
                self.user_repo.link_faceit_account,
                telegram_user_id,
                faceit_player.player_id,
                faceit_player.nickname
            )
            
            if not result:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Update activity
            await self._update_user_activity(telegram_user_id)
            
            # Publish event
            await self.publish_event(
                EventType.USER_UPDATED,
                result.id,
                {
                    "action": "faceit_linked",
                    "faceit_player_id": faceit_player.player_id,
                    "faceit_nickname": faceit_player.nickname
                }
            )
            
            return ServiceResult.success_result(
                result,
                metadata={"faceit_player": faceit_player.dict()},
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            logger.error(f"Error linking FACEIT account: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to link FACEIT account: {e}", "FACEIT_LINK_ERROR")
            )
    
    async def unlink_faceit_account(
        self,
        telegram_user_id: int,
        confirm: bool = False
    ) -> ServiceResult[User]:
        """
        Unlink FACEIT account from user.
        
        Args:
            telegram_user_id: Telegram user ID
            confirm: Confirmation flag for safety
            
        Returns:
            ServiceResult with updated user
        """
        if not confirm:
            return ServiceResult.validation_error(
                "Account unlinking must be confirmed",
                "confirm"
            )
        
        try:
            result, processing_time = await self.measure_performance(
                "unlink_faceit_account",
                self.user_repo.unlink_faceit_account,
                telegram_user_id
            )
            
            if not result:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Clear user-specific caches
            await self.invalidate_cache_pattern(f"users:telegram:{telegram_user_id}*")
            await self.invalidate_cache_pattern(f"stats:user:{result.id}*")
            
            # Publish event
            await self.publish_event(
                EventType.USER_UPDATED,
                result.id,
                {"action": "faceit_unlinked"}
            )
            
            return ServiceResult.success_result(
                result,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            logger.error(f"Error unlinking FACEIT account: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to unlink FACEIT account: {e}", "FACEIT_UNLINK_ERROR")
            )
    
    # User profile and preferences
    async def get_user_profile(
        self,
        telegram_user_id: int,
        include_subscription: bool = True,
        include_stats: bool = False
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Get comprehensive user profile.
        
        Args:
            telegram_user_id: Telegram user ID
            include_subscription: Include subscription data
            include_stats: Include user statistics
            
        Returns:
            ServiceResult with user profile data
        """
        try:
            cache_key = f"profile:{telegram_user_id}:{include_subscription}:{include_stats}"
            
            profile_data, processing_time = await self.measure_performance(
                "get_user_profile",
                self.with_cache,
                cache_key,
                self._fetch_user_profile,
                300,  # TTL
                telegram_user_id,
                include_subscription,
                include_stats
            )
            
            if not profile_data:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            return ServiceResult.success_result(
                profile_data,
                processing_time_ms=processing_time
            )
            
        except Exception as e:
            logger.error(f"Error getting user profile: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to get user profile: {e}", "PROFILE_ERROR")
            )
    
    async def _fetch_user_profile(
        self,
        telegram_user_id: int,
        include_subscription: bool,
        include_stats: bool
    ) -> Optional[Dict[str, Any]]:
        """Fetch user profile data."""
        user = await self.user_repo.get_by_telegram_id(telegram_user_id)
        if not user:
            return None
        
        profile = {
            "user_id": user.user_id,
            "faceit_player_id": user.faceit_player_id,
            "faceit_nickname": user.faceit_nickname,
            "language": user.language,
            "notifications_enabled": user.notifications_enabled,
            "created_at": user.created_at,
            "last_active_at": user.last_active_at,
            "total_requests": user.total_requests,
            "waiting_for_nickname": user.waiting_for_nickname
        }
        
        # Include subscription data
        if include_subscription:
            subscription = await self.subscription_repo.get_by_user_id(user.id)
            if subscription:
                profile["subscription"] = {
                    "tier": subscription.tier.value,
                    "expires_at": subscription.expires_at,
                    "auto_renew": subscription.auto_renew,
                    "daily_requests": subscription.daily_requests,
                    "last_reset_date": subscription.last_reset_date,
                    "referral_code": subscription.referral_code,
                    "referrals_count": subscription.referrals_count
                }
        
        # Include user statistics
        if include_stats and user.faceit_player_id:
            try:
                faceit_player = await self.faceit_api.get_player_by_id(user.faceit_player_id)
                if faceit_player:
                    profile["faceit_stats"] = {
                        "skill_level": faceit_player.games.get('cs2', {}).skill_level if faceit_player.games.get('cs2') else 0,
                        "faceit_elo": faceit_player.games.get('cs2', {}).faceit_elo if faceit_player.games.get('cs2') else 0,
                        "region": faceit_player.games.get('cs2', {}).region if faceit_player.games.get('cs2') else None,
                        "avatar": faceit_player.avatar,
                        "country": faceit_player.country
                    }
            except FaceitAPIError as e:
                logger.warning(f"Failed to fetch FACEIT stats for user {user.user_id}: {e}")
        
        return profile
    
    async def update_user_preferences(
        self,
        telegram_user_id: int,
        preferences: Dict[str, Any]
    ) -> ServiceResult[User]:
        """
        Update user preferences.
        
        Args:
            telegram_user_id: Telegram user ID
            preferences: Dictionary of preferences to update
            
        Returns:
            ServiceResult with updated user
        """
        try:
            # Validate preferences
            allowed_preferences = {
                "language": {"type": str, "max_length": 10},
                "notifications_enabled": {"type": bool}
            }
            
            # Filter to only allowed preferences
            filtered_preferences = {
                key: value for key, value in preferences.items()
                if key in allowed_preferences
            }
            
            if not filtered_preferences:
                return ServiceResult.validation_error(
                    "No valid preferences provided",
                    "preferences"
                )
            
            self.validate_field_constraints(filtered_preferences, allowed_preferences)
            
            # Update user
            user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            result, processing_time = await self.measure_performance(
                "update_user_preferences",
                self.user_repo.update,
                user.id,
                filtered_preferences
            )
            
            # Invalidate cache
            await self.invalidate_cache_pattern(f"profile:{telegram_user_id}*")
            
            # Publish event
            await self.publish_event(
                EventType.USER_UPDATED,
                user.id,
                {
                    "action": "preferences_updated",
                    "updated_preferences": filtered_preferences
                }
            )
            
            return ServiceResult.success_result(
                result,
                processing_time_ms=processing_time
            )
            
        except ValidationError as e:
            return ServiceResult.error_result(e)
        except Exception as e:
            logger.error(f"Error updating user preferences: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to update preferences: {e}", "PREFERENCE_UPDATE_ERROR")
            )
    
    # Activity tracking
    async def update_activity(
        self,
        telegram_user_id: int,
        action: str = "general",
        metadata: Optional[Dict[str, Any]] = None
    ) -> ServiceResult[bool]:
        """
        Update user activity tracking.
        
        Args:
            telegram_user_id: Telegram user ID
            action: Action type being tracked
            metadata: Optional metadata about the action
            
        Returns:
            ServiceResult with success status
        """
        try:
            await self._update_user_activity(telegram_user_id, action, metadata)
            
            return ServiceResult.success_result(
                True,
                metadata={"action": action, "telegram_user_id": telegram_user_id}
            )
            
        except Exception as e:
            logger.error(f"Error updating user activity: {e}")
            # Don't fail the operation for activity tracking errors
            return ServiceResult.success_result(False)
    
    async def _update_user_activity(
        self,
        telegram_user_id: int,
        action: str = "general",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Internal method to update user activity."""
        try:
            await self.user_repo.update_last_activity(telegram_user_id)
            
            # Track activity in cache for analytics
            activity_key = f"activity:{telegram_user_id}:{datetime.now().date()}"
            if self.cache:
                try:
                    current_activity = await self.cache.get(activity_key) or {}
                    if not isinstance(current_activity, dict):
                        current_activity = {}
                    
                    current_activity[action] = current_activity.get(action, 0) + 1
                    current_activity["last_action"] = datetime.now().isoformat()
                    
                    await self.cache.set(activity_key, current_activity, 86400)  # 24 hours
                except Exception as e:
                    logger.warning(f"Failed to track activity in cache: {e}")
        
        except Exception as e:
            logger.warning(f"Failed to update user activity: {e}")
    
    # FACEIT integration helpers
    async def _validate_faceit_player(self, nickname: str) -> ServiceResult[FaceitPlayer]:
        """
        Validate and fetch FACEIT player data.
        
        Args:
            nickname: FACEIT nickname to validate
            
        Returns:
            ServiceResult with FaceitPlayer or error
        """
        if not nickname or not nickname.strip():
            return ServiceResult.validation_error("FACEIT nickname is required", "faceit_nickname")
        
        nickname = nickname.strip()
        
        # Validate nickname format
        if not re.match(r"^[a-zA-Z0-9_-]{1,50}$", nickname):
            return ServiceResult.validation_error(
                "Invalid FACEIT nickname format. Use only letters, numbers, underscore and dash",
                "faceit_nickname"
            )
        
        try:
            # Fetch player data from FACEIT API
            faceit_player = await self.faceit_api.get_player_by_nickname(nickname)
            if not faceit_player:
                return ServiceResult.business_rule_error(
                    f"FACEIT player '{nickname}' not found",
                    "FACEIT_PLAYER_NOT_FOUND"
                )
            
            # Validate player has CS2 data
            if not faceit_player.games or 'cs2' not in faceit_player.games:
                return ServiceResult.business_rule_error(
                    f"Player '{nickname}' has no CS2 statistics",
                    "NO_CS2_DATA"
                )
            
            return ServiceResult.success_result(faceit_player)
            
        except FaceitAPIError as e:
            logger.error(f"FACEIT API error validating player '{nickname}': {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to validate FACEIT player: {e}", "FACEIT_API_ERROR")
            )
        except Exception as e:
            logger.error(f"Unexpected error validating FACEIT player '{nickname}': {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to validate FACEIT player: {e}", "VALIDATION_ERROR")
            )
    
    # Legacy data migration
    async def _migrate_legacy_user_data(self, telegram_user_id: int, new_user_id: uuid.UUID):
        """Migrate data from legacy JSON storage to database."""
        try:
            legacy_user = await legacy_storage.get_user(telegram_user_id)
            if not legacy_user:
                return
            
            # Update subscription data if exists
            if legacy_user.subscription:
                subscription = await self.subscription_repo.get_by_user_id(new_user_id)
                if subscription:
                    # Migrate subscription data
                    update_data = {}
                    
                    if legacy_user.subscription.tier != SubscriptionTier.FREE:
                        update_data["tier"] = legacy_user.subscription.tier
                        update_data["expires_at"] = legacy_user.subscription.expires_at
                        update_data["auto_renew"] = legacy_user.subscription.auto_renew
                        update_data["payment_method"] = legacy_user.subscription.payment_method
                    
                    if legacy_user.subscription.daily_requests > 0:
                        update_data["daily_requests"] = legacy_user.subscription.daily_requests
                        update_data["last_reset_date"] = legacy_user.subscription.last_reset_date
                    
                    if legacy_user.subscription.referral_code:
                        update_data["referral_code"] = legacy_user.subscription.referral_code
                        update_data["referrals_count"] = legacy_user.subscription.referrals_count
                    
                    if legacy_user.subscription.referred_by:
                        update_data["referred_by_user_id"] = legacy_user.subscription.referred_by
                    
                    if update_data:
                        await self.subscription_repo.update(subscription.id, update_data)
            
            logger.info(f"Migrated legacy data for user {telegram_user_id}")
            
        except Exception as e:
            logger.warning(f"Failed to migrate legacy data for user {telegram_user_id}: {e}")
    
    # User search and listing
    async def search_users(
        self,
        query: Optional[str] = None,
        faceit_only: bool = False,
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> ServiceResult[List[Dict[str, Any]]]:
        """
        Search users with various filters.
        
        Args:
            query: Search query (nickname or partial match)
            faceit_only: Only return users with linked FACEIT accounts
            active_only: Only return recently active users
            limit: Maximum results to return
            offset: Number of results to skip
            
        Returns:
            ServiceResult with list of user data
        """
        try:
            # Validate parameters
            if limit > 100:
                limit = 100
            
            if query:
                # Search by nickname
                users = await self.user_repo.search_users_by_nickname(query, limit)
            elif faceit_only:
                users = await self.user_repo.get_users_with_faceit_accounts(offset, limit)
            elif active_only:
                users = await self.user_repo.get_active_users(7, offset, limit)
            else:
                users = await self.user_repo.get_all(offset, limit, order_by="created_at", order_desc=True)
            
            # Convert to dictionaries for response
            user_data = []
            for user in users:
                user_dict = {
                    "telegram_user_id": user.user_id,
                    "faceit_nickname": user.faceit_nickname,
                    "language": user.language,
                    "created_at": user.created_at,
                    "last_active_at": user.last_active_at,
                    "total_requests": user.total_requests
                }
                user_data.append(user_dict)
            
            return ServiceResult.success_result(
                user_data,
                metadata={"count": len(user_data), "query": query}
            )
            
        except Exception as e:
            logger.error(f"Error searching users: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to search users: {e}", "USER_SEARCH_ERROR")
            )
    
    async def get_user_statistics(
        self,
        telegram_user_id: Optional[int] = None
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Get user statistics.
        
        Args:
            telegram_user_id: Optional specific user ID, if None returns global stats
            
        Returns:
            ServiceResult with statistics
        """
        try:
            if telegram_user_id:
                # Get specific user stats
                user = await self.user_repo.get_by_telegram_id(telegram_user_id)
                if not user:
                    return ServiceResult.business_rule_error(
                        f"User with Telegram ID {telegram_user_id} not found",
                        "USER_NOT_FOUND"
                    )
                
                stats = {
                    "user_id": user.user_id,
                    "created_at": user.created_at,
                    "total_requests": user.total_requests,
                    "last_active_at": user.last_active_at,
                    "faceit_linked": user.faceit_player_id is not None,
                    "language": user.language
                }
                
                # Get match history count
                match_history = await self.user_repo.get_user_match_history(user.user_id, 1000)
                stats["total_matches_analyzed"] = len(match_history)
                
            else:
                # Get global user statistics
                stats = await self.user_repo.get_user_stats()
            
            return ServiceResult.success_result(stats)
            
        except Exception as e:
            logger.error(f"Error getting user statistics: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to get user statistics: {e}", "STATS_ERROR")
            )
    
    # Health check implementation
    async def health_check(self) -> ServiceResult[Dict[str, Any]]:
        """Perform user service health check."""
        try:
            health_data = await self._base_health_check()
            
            # Test database connectivity
            try:
                user_count = await self.user_repo.count()
                health_data["database_status"] = "connected"
                health_data["total_users"] = user_count
            except Exception as e:
                health_data["database_status"] = f"error: {e}"
                health_data["status"] = "degraded"
            
            # Test FACEIT API connectivity
            try:
                test_player = await self.faceit_api.get_player_by_nickname("s1mple")
                health_data["faceit_api_status"] = "connected" if test_player else "no_data"
            except Exception as e:
                health_data["faceit_api_status"] = f"error: {e}"
                health_data["status"] = "degraded"
            
            return ServiceResult.success_result(health_data)
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Health check failed: {e}", "HEALTH_CHECK_ERROR")
            )