"""
Bot Integration Adapter for seamless service integration.

Provides integration layer between bot handlers and both legacy JSON
storage and new PostgreSQL ORM services with automatic fallback.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from aiogram.types import Message, CallbackQuery

from utils.storage import UserData, SubscriptionTier
from services.user import UserService
from services.subscription import SubscriptionService
from services.match import MatchService
from services.analytics import AnalyticsService
from faceit.api import FaceitAPI
from .storage_adapter import StorageAdapter, StorageBackend

logger = logging.getLogger(__name__)


class BotIntegrationAdapter:
    """
    Integration adapter for bot handlers to use new services with fallback.
    
    Provides unified interface for bot handlers to work with both legacy
    JSON storage and new PostgreSQL services seamlessly.
    """
    
    def __init__(
        self,
        storage_adapter: StorageAdapter,
        user_service: Optional[UserService] = None,
        subscription_service: Optional[SubscriptionService] = None,
        match_service: Optional[MatchService] = None,
        analytics_service: Optional[AnalyticsService] = None,
        faceit_api: Optional[FaceitAPI] = None
    ):
        """
        Initialize bot integration adapter.
        
        Args:
            storage_adapter: Storage adapter instance
            user_service: PostgreSQL user service
            subscription_service: PostgreSQL subscription service
            match_service: PostgreSQL match service
            analytics_service: PostgreSQL analytics service
            faceit_api: FACEIT API client
        """
        self.storage = storage_adapter
        self.user_service = user_service
        self.subscription_service = subscription_service
        self.match_service = match_service
        self.analytics_service = analytics_service
        self.faceit_api = faceit_api
        
        self._service_availability = {
            "user_service": user_service is not None,
            "subscription_service": subscription_service is not None,
            "match_service": match_service is not None,
            "analytics_service": analytics_service is not None
        }
        
        logger.info(f"BotIntegrationAdapter initialized. Services available: {self._service_availability}")
    
    # User management methods
    async def get_or_create_user(
        self,
        telegram_user_id: int,
        faceit_nickname: Optional[str] = None,
        language: str = "ru",
        referral_code: Optional[str] = None
    ) -> Optional[UserData]:
        """
        Get existing user or create new one.
        
        Args:
            telegram_user_id: Telegram user ID
            faceit_nickname: Optional FACEIT nickname
            language: User language preference
            referral_code: Optional referral code
            
        Returns:
            UserData instance or None if creation failed
        """
        try:
            # Try to get existing user
            user = await self.storage.get_user(telegram_user_id)
            if user:
                return user
            
            # Create new user using services if available
            if self.user_service:
                result = await self.user_service.create_user(
                    telegram_user_id,
                    faceit_nickname,
                    language,
                    referral_code
                )
                
                if result.success:
                    # Convert service result to UserData
                    user_data = UserData(
                        user_id=telegram_user_id,
                        faceit_nickname=faceit_nickname,
                        language=language
                    )
                    return user_data
            
            # Fallback to direct storage creation
            user_data = UserData(
                user_id=telegram_user_id,
                faceit_nickname=faceit_nickname,
                language=language
            )
            
            success = await self.storage.save_user(user_data)
            if success:
                # Apply referral if provided
                if referral_code:
                    await self.storage.apply_referral(telegram_user_id, referral_code)
                
                return user_data
            
            return None
        
        except Exception as e:
            logger.error(f"Error getting or creating user {telegram_user_id}: {e}")
            return None
    
    async def link_faceit_account(
        self,
        telegram_user_id: int,
        faceit_nickname: str
    ) -> tuple[bool, Optional[str]]:
        """
        Link FACEIT account to user.
        
        Args:
            telegram_user_id: Telegram user ID
            faceit_nickname: FACEIT nickname to link
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Use service if available
            if self.user_service:
                result = await self.user_service.link_faceit_account(
                    telegram_user_id, faceit_nickname
                )
                
                if result.success:
                    return True, None
                else:
                    return False, result.error.message if result.error else "Unknown error"
            
            # Fallback to storage adapter
            user = await self.storage.get_user(telegram_user_id)
            if not user:
                return False, "User not found"
            
            # Validate FACEIT player
            if self.faceit_api:
                try:
                    player = await self.faceit_api.get_player_by_nickname(faceit_nickname)
                    if not player:
                        return False, f"FACEIT player '{faceit_nickname}' not found"
                    
                    user.faceit_player_id = player.player_id
                    user.faceit_nickname = player.nickname
                except Exception as e:
                    return False, f"FACEIT API error: {e}"
            else:
                user.faceit_nickname = faceit_nickname
            
            success = await self.storage.save_user(user)
            return success, None if success else "Failed to save user"
        
        except Exception as e:
            logger.error(f"Error linking FACEIT account for user {telegram_user_id}: {e}")
            return False, str(e)
    
    async def update_user_activity(
        self,
        telegram_user_id: int,
        action: str = "general",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update user activity tracking.
        
        Args:
            telegram_user_id: Telegram user ID
            action: Action type
            metadata: Optional action metadata
            
        Returns:
            Success status
        """
        try:
            # Use service if available
            if self.user_service:
                result = await self.user_service.update_activity(
                    telegram_user_id, action, metadata
                )
                return result.success
            
            # Fallback to basic activity update
            user = await self.storage.get_user(telegram_user_id)
            if user:
                user.last_active_at = datetime.now()
                user.total_requests += 1
                return await self.storage.save_user(user)
            
            return False
        
        except Exception as e:
            logger.error(f"Error updating activity for user {telegram_user_id}: {e}")
            return False
    
    # Subscription management methods
    async def check_subscription_access(
        self,
        telegram_user_id: int,
        required_tier: SubscriptionTier = SubscriptionTier.PREMIUM
    ) -> tuple[bool, Optional[str]]:
        """
        Check if user has required subscription access.
        
        Args:
            telegram_user_id: Telegram user ID
            required_tier: Required subscription tier
            
        Returns:
            Tuple of (has_access, reason_if_denied)
        """
        try:
            # Use service if available
            if self.subscription_service:
                result = await self.subscription_service.check_subscription_access(
                    telegram_user_id, required_tier
                )
                
                if result.success:
                    return result.data, None
                else:
                    return False, result.error.message if result.error else "Access denied"
            
            # Fallback to storage adapter
            user = await self.storage.get_user(telegram_user_id)
            if not user:
                return False, "User not found"
            
            # Simple tier comparison
            user_tier_value = {
                SubscriptionTier.FREE: 0,
                SubscriptionTier.PREMIUM: 1,
                SubscriptionTier.PRO: 2
            }.get(user.subscription.tier, 0)
            
            required_tier_value = {
                SubscriptionTier.FREE: 0,
                SubscriptionTier.PREMIUM: 1,
                SubscriptionTier.PRO: 2
            }.get(required_tier, 1)
            
            if user_tier_value >= required_tier_value:
                return True, None
            else:
                return False, f"Requires {required_tier.value} subscription"
        
        except Exception as e:
            logger.error(f"Error checking subscription access for user {telegram_user_id}: {e}")
            return False, str(e)
    
    async def check_rate_limit(self, telegram_user_id: int) -> tuple[bool, Optional[str]]:
        """
        Check if user can make a request (rate limiting).
        
        Args:
            telegram_user_id: Telegram user ID
            
        Returns:
            Tuple of (can_make_request, reason_if_denied)
        """
        try:
            # Use service if available
            if self.subscription_service:
                result = await self.subscription_service.can_make_request(telegram_user_id)
                
                if result.success:
                    return result.data, None
                else:
                    return False, result.error.message if result.error else "Rate limit exceeded"
            
            # Fallback to storage adapter
            can_request = await self.storage.can_make_request(telegram_user_id)
            if can_request:
                await self.storage.increment_request_count(telegram_user_id)
                return True, None
            else:
                return False, "Daily request limit exceeded"
        
        except Exception as e:
            logger.error(f"Error checking rate limit for user {telegram_user_id}: {e}")
            # Default to allowing request if check fails
            return True, None
    
    async def format_subscription_status(self, telegram_user_id: int) -> str:
        """
        Format subscription status message for user.
        
        Args:
            telegram_user_id: Telegram user ID
            
        Returns:
            Formatted subscription status message
        """
        try:
            # Use service if available
            if self.subscription_service:
                result = await self.subscription_service.get_subscription_status(telegram_user_id)
                
                if result.success:
                    status = result.data
                    message = f"💎 <b>Статус подписки</b>\n\n"
                    message += f"📊 <b>Тариф:</b> {status['tier_display']}\n"
                    
                    if status.get('expires_at'):
                        message += f"⏰ <b>Действует до:</b> {status['expires_at'].strftime('%d.%m.%Y')}\n"
                    
                    message += f"📈 <b>Запросов сегодня:</b> {status['daily_requests']}/{status['daily_limit']}\n"
                    message += f"📋 <b>Всего запросов:</b> {status['total_requests']}\n"
                    
                    return message
            
            # Fallback to basic status
            user = await self.storage.get_user(telegram_user_id)
            if not user:
                return "❌ Пользователь не найден"
            
            message = f"💎 <b>Статус подписки</b>\n\n"
            message += f"📊 <b>Тариф:</b> {user.subscription.tier.value.upper()}\n"
            
            if user.subscription.expires_at:
                message += f"⏰ <b>Действует до:</b> {user.subscription.expires_at.strftime('%d.%m.%Y')}\n"
            
            message += f"📈 <b>Запросов сегодня:</b> {user.subscription.daily_requests}\n"
            message += f"📋 <b>Всего запросов:</b> {user.total_requests}\n"
            
            return message
        
        except Exception as e:
            logger.error(f"Error formatting subscription status for user {telegram_user_id}: {e}")
            return "❌ Ошибка при получении статуса подписки"
    
    # Match analysis integration
    async def analyze_match(
        self,
        match_url: str,
        telegram_user_id: Optional[int] = None
    ) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Analyze FACEIT match.
        
        Args:
            match_url: FACEIT match URL
            telegram_user_id: Optional user ID for tracking
            
        Returns:
            Tuple of (success, error_message, analysis_data)
        """
        try:
            # Use service if available
            if self.match_service:
                result = await self.match_service.analyze_match(match_url, telegram_user_id)
                
                if result.success:
                    return True, None, result.data
                else:
                    return False, result.error.message if result.error else "Analysis failed", None
            
            # Fallback to existing match analyzer
            from utils.match_analyzer import MatchAnalyzer
            
            if self.faceit_api:
                analyzer = MatchAnalyzer(self.faceit_api)
                analysis_result = await analyzer.analyze_match(match_url)
                return True, None, analysis_result
            
            return False, "Match analysis not available", None
        
        except Exception as e:
            logger.error(f"Error analyzing match: {e}")
            return False, str(e), None
    
    # Analytics and statistics
    async def get_user_statistics(
        self,
        telegram_user_id: int,
        include_faceit_stats: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get comprehensive user statistics.
        
        Args:
            telegram_user_id: Telegram user ID
            include_faceit_stats: Whether to include FACEIT statistics
            
        Returns:
            User statistics dictionary or None
        """
        try:
            # Use service if available
            if self.analytics_service:
                result = await self.analytics_service.get_user_analytics(
                    telegram_user_id, include_faceit_stats
                )
                
                if result.success:
                    return result.data
            
            # Fallback to basic user data
            user = await self.storage.get_user(telegram_user_id)
            if not user:
                return None
            
            stats = {
                "user_id": user.user_id,
                "created_at": user.created_at,
                "total_requests": user.total_requests,
                "last_active_at": user.last_active_at,
                "faceit_linked": user.faceit_player_id is not None,
                "language": user.language,
                "subscription_tier": user.subscription.tier.value
            }
            
            # Add FACEIT stats if requested and available
            if include_faceit_stats and user.faceit_player_id and self.faceit_api:
                try:
                    player = await self.faceit_api.get_player_by_id(user.faceit_player_id)
                    if player:
                        cs2_stats = player.games.get('cs2', {}) if player.games else {}
                        stats["faceit_stats"] = {
                            "skill_level": getattr(cs2_stats, 'skill_level', 0),
                            "faceit_elo": getattr(cs2_stats, 'faceit_elo', 0),
                            "region": getattr(cs2_stats, 'region', None)
                        }
                except Exception as e:
                    logger.warning(f"Failed to get FACEIT stats for user {telegram_user_id}: {e}")
            
            return stats
        
        except Exception as e:
            logger.error(f"Error getting user statistics for {telegram_user_id}: {e}")
            return None
    
    async def track_command_usage(
        self,
        telegram_user_id: int,
        command: str,
        success: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Track command usage for analytics.
        
        Args:
            telegram_user_id: Telegram user ID
            command: Command that was used
            success: Whether command execution was successful
            metadata: Optional command metadata
            
        Returns:
            Success status
        """
        try:
            # Use service if available
            if self.analytics_service:
                result = await self.analytics_service.track_command_usage(
                    telegram_user_id, command, success, metadata
                )
                return result.success
            
            # Fallback to activity tracking
            return await self.update_user_activity(
                telegram_user_id, 
                f"command_{command}",
                {"success": success, "metadata": metadata}
            )
        
        except Exception as e:
            logger.error(f"Error tracking command usage: {e}")
            return False
    
    # System health and diagnostics
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on all integrated services.
        
        Returns:
            Health status information
        """
        health = {
            "timestamp": datetime.now().isoformat(),
            "storage_adapter": await self.storage.health_check(),
            "services": {}
        }
        
        # Check each service
        for service_name, service in [
            ("user_service", self.user_service),
            ("subscription_service", self.subscription_service),
            ("match_service", self.match_service),
            ("analytics_service", self.analytics_service)
        ]:
            if service:
                try:
                    service_health = await service.health_check()
                    health["services"][service_name] = service_health.data if service_health.success else {"status": "error", "error": str(service_health.error)}
                except Exception as e:
                    health["services"][service_name] = {"status": "error", "error": str(e)}
            else:
                health["services"][service_name] = {"status": "not_available"}
        
        return health
    
    def get_service_info(self) -> Dict[str, Any]:
        """
        Get information about available services.
        
        Returns:
            Service availability information
        """
        return {
            "storage_backend": self.storage.backend.value,
            "service_availability": self._service_availability,
            "storage_info": self.storage.get_backend_info()
        }
    
    # Context management for handlers
    async def with_user_context(
        self,
        telegram_user_id: int,
        handler_func,
        *args,
        **kwargs
    ):
        """
        Execute handler function with user context and error handling.
        
        Args:
            telegram_user_id: Telegram user ID
            handler_func: Handler function to execute
            *args: Positional arguments for handler
            **kwargs: Keyword arguments for handler
            
        Returns:
            Handler function result
        """
        try:
            # Update user activity
            await self.update_user_activity(telegram_user_id, "handler_execution")
            
            # Execute handler
            result = await handler_func(*args, **kwargs)
            
            # Track successful execution
            await self.track_command_usage(
                telegram_user_id,
                handler_func.__name__,
                success=True
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Error in handler {handler_func.__name__} for user {telegram_user_id}: {e}")
            
            # Track failed execution
            await self.track_command_usage(
                telegram_user_id,
                handler_func.__name__,
                success=False,
                metadata={"error": str(e)}
            )
            
            raise