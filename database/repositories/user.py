"""
User Repository implementation with FACEIT integration.

Provides user management functionality including:
- User CRUD operations with FACEIT integration
- Subscription management integration
- Activity tracking and analytics
- Cache management for user data
- Relationship management with subscriptions and matches
"""

import logging
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timedelta
import uuid

from sqlalchemy import select, and_, func, desc
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from database.models import User, UserSubscription, MatchAnalysis, Payment, SubscriptionTier
from database.connection import DatabaseOperationError
from utils.redis_cache import player_cache
from .base import BaseRepository

logger = logging.getLogger(__name__)


class UserCreateData:
    """Data class for creating users."""
    def __init__(
        self,
        user_id: int,
        faceit_player_id: Optional[str] = None,
        faceit_nickname: Optional[str] = None,
        language: str = "ru",
        notifications_enabled: bool = True
    ):
        self.user_id = user_id
        self.faceit_player_id = faceit_player_id
        self.faceit_nickname = faceit_nickname
        self.language = language
        self.notifications_enabled = notifications_enabled


class UserUpdateData:
    """Data class for updating users."""
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class UserRepository(BaseRepository[User, UserCreateData, UserUpdateData]):
    """
    Repository for User entity management.
    
    Provides comprehensive user management with:
    - FACEIT account integration
    - Subscription management
    - Activity tracking
    - Relationship management
    - Performance optimizations with caching
    """
    
    def __init__(self):
        """Initialize user repository with Redis cache."""
        super().__init__(User, player_cache)
    
    # Core user operations
    async def get_by_telegram_id(self, user_id: int) -> Optional[User]:
        """
        Get user by Telegram user ID.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            User instance or None if not found
        """
        cache_key = self._cache_key("telegram", user_id)
        
        # Try cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            async with self.get_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                # Cache result
                if user:
                    await self._set_cache(cache_key, user, 300)
                
                return user
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_by_telegram_id: {e}")
            raise DatabaseOperationError(f"Failed to get user by telegram id: {e}")
    
    async def get_by_faceit_id(self, faceit_player_id: str) -> Optional[User]:
        """
        Get user by FACEIT player ID.
        
        Args:
            faceit_player_id: FACEIT player ID
            
        Returns:
            User instance or None if not found
        """
        cache_key = self._cache_key("faceit", faceit_player_id)
        
        # Try cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            async with self.get_session() as session:
                stmt = select(User).where(User.faceit_player_id == faceit_player_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                # Cache result
                if user:
                    await self._set_cache(cache_key, user, 300)
                
                return user
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_by_faceit_id: {e}")
            raise DatabaseOperationError(f"Failed to get user by faceit id: {e}")
    
    async def get_by_nickname(self, faceit_nickname: str) -> Optional[User]:
        """
        Get user by FACEIT nickname.
        
        Args:
            faceit_nickname: FACEIT nickname
            
        Returns:
            User instance or None if not found
        """
        cache_key = self._cache_key("nickname", faceit_nickname.lower())
        
        # Try cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            async with self.get_session() as session:
                stmt = select(User).where(
                    func.lower(User.faceit_nickname) == faceit_nickname.lower()
                )
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                # Cache result
                if user:
                    await self._set_cache(cache_key, user, 300)
                
                return user
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_by_nickname: {e}")
            raise DatabaseOperationError(f"Failed to get user by nickname: {e}")
    
    async def create_user(
        self,
        user_id: int,
        faceit_player_id: Optional[str] = None,
        faceit_nickname: Optional[str] = None,
        language: str = "ru"
    ) -> User:
        """
        Create new user with automatic subscription creation.
        
        Args:
            user_id: Telegram user ID
            faceit_player_id: Optional FACEIT player ID
            faceit_nickname: Optional FACEIT nickname
            language: User language preference
            
        Returns:
            Created user instance
        """
        try:
            async with self.get_session() as session:
                # Check if user already exists
                existing_user = await self.get_by_telegram_id(user_id)
                if existing_user:
                    logger.info(f"User {user_id} already exists")
                    return existing_user
                
                # Create user
                user = User(
                    user_id=user_id,
                    faceit_player_id=faceit_player_id,
                    faceit_nickname=faceit_nickname,
                    language=language,
                    created_at=datetime.now(),
                    last_active_at=datetime.now()
                )
                
                session.add(user)
                await session.flush()
                
                # Create default subscription
                subscription = UserSubscription(
                    user_id=user.id,
                    tier=SubscriptionTier.FREE,
                    created_at=datetime.now()
                )
                
                session.add(subscription)
                await session.flush()
                await session.refresh(user)
                
                # Invalidate caches
                await self._invalidate_cache("users:*")
                await self._invalidate_cache("subscriptions:*")
                
                logger.info(f"Created user {user_id} with id: {user.id}")
                return user
                
        except IntegrityError as e:
            logger.error(f"User creation integrity error: {e}")
            # Try to get existing user in case of race condition
            existing_user = await self.get_by_telegram_id(user_id)
            if existing_user:
                return existing_user
            raise DatabaseOperationError(f"Failed to create user: Duplicate user_id")
        except SQLAlchemyError as e:
            logger.error(f"Database error in create_user: {e}")
            raise DatabaseOperationError(f"Failed to create user: {e}")
    
    async def link_faceit_account(
        self,
        user_id: int,
        faceit_player_id: str,
        faceit_nickname: str
    ) -> Optional[User]:
        """
        Link FACEIT account to existing user.
        
        Args:
            user_id: Telegram user ID
            faceit_player_id: FACEIT player ID
            faceit_nickname: FACEIT nickname
            
        Returns:
            Updated user or None if not found
        """
        try:
            async with self.get_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    return None
                
                # Update FACEIT information
                user.faceit_player_id = faceit_player_id
                user.faceit_nickname = faceit_nickname
                user.updated_at = datetime.now()
                user.last_active_at = datetime.now()
                
                await session.flush()
                await session.refresh(user)
                
                # Invalidate caches
                await self._invalidate_cache("users:*")
                
                logger.info(f"Linked FACEIT account {faceit_nickname} to user {user_id}")
                return user
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in link_faceit_account: {e}")
            raise DatabaseOperationError(f"Failed to link FACEIT account: {e}")
    
    async def unlink_faceit_account(self, user_id: int) -> Optional[User]:
        """
        Unlink FACEIT account from user.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Updated user or None if not found
        """
        try:
            async with self.get_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    return None
                
                # Clear FACEIT information
                user.faceit_player_id = None
                user.faceit_nickname = None
                user.last_checked_match_id = None
                user.updated_at = datetime.now()
                
                await session.flush()
                await session.refresh(user)
                
                # Invalidate caches
                await self._invalidate_cache("users:*")
                
                logger.info(f"Unlinked FACEIT account from user {user_id}")
                return user
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in unlink_faceit_account: {e}")
            raise DatabaseOperationError(f"Failed to unlink FACEIT account: {e}")
    
    # Activity and analytics
    async def update_last_activity(self, user_id: int) -> None:
        """
        Update user's last activity timestamp.
        
        Args:
            user_id: Telegram user ID
        """
        try:
            async with self.get_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                if user:
                    user.last_active_at = datetime.now()
                    user.total_requests += 1
                    
                    await session.flush()
                    
                    # Invalidate cache
                    await self._invalidate_cache(f"users:telegram:{user_id}")
                    
        except SQLAlchemyError as e:
            logger.error(f"Database error in update_last_activity: {e}")
            # Don't raise exception for activity updates
    
    async def update_last_checked_match(
        self,
        user_id: int,
        match_id: str
    ) -> Optional[User]:
        """
        Update user's last checked match ID.
        
        Args:
            user_id: Telegram user ID
            match_id: Match ID
            
        Returns:
            Updated user or None if not found
        """
        try:
            async with self.get_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    return None
                
                user.last_checked_match_id = match_id
                user.updated_at = datetime.now()
                
                await session.flush()
                await session.refresh(user)
                
                # Invalidate cache
                await self._invalidate_cache(f"users:telegram:{user_id}")
                
                return user
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in update_last_checked_match: {e}")
            raise DatabaseOperationError(f"Failed to update last checked match: {e}")
    
    # User lists and filtering
    async def get_users_with_faceit_accounts(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> List[User]:
        """
        Get users who have linked FACEIT accounts.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records
            
        Returns:
            List of users with FACEIT accounts
        """
        return await self.get_all(
            skip=skip,
            limit=limit,
            filters={
                'faceit_player_id': {'not_null': True}
            },
            order_by='last_active_at',
            order_desc=True
        )
    
    async def get_active_users(
        self,
        since_days: int = 7,
        skip: int = 0,
        limit: int = 100
    ) -> List[User]:
        """
        Get users active within specified number of days.
        
        Args:
            since_days: Number of days to look back
            skip: Number of records to skip
            limit: Maximum number of records
            
        Returns:
            List of active users
        """
        since_date = datetime.now() - timedelta(days=since_days)
        
        return await self.get_all(
            skip=skip,
            limit=limit,
            filters={
                'last_active_at': {'gte': since_date}
            },
            order_by='last_active_at',
            order_desc=True
        )
    
    async def search_users_by_nickname(
        self,
        nickname_pattern: str,
        limit: int = 50
    ) -> List[User]:
        """
        Search users by FACEIT nickname pattern.
        
        Args:
            nickname_pattern: Nickname search pattern
            limit: Maximum number of results
            
        Returns:
            List of matching users
        """
        return await self.get_all(
            limit=limit,
            filters={
                'faceit_nickname': {'like': nickname_pattern}
            },
            order_by='last_active_at',
            order_desc=True
        )
    
    # Relationships and complex queries
    async def get_user_with_subscription(self, user_id: int) -> Optional[User]:
        """
        Get user with loaded subscription data.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            User with subscription or None if not found
        """
        user = await self.get_by_telegram_id(user_id)
        if not user:
            return None
        
        return await self.get_with_relationships(
            user.id,
            ['subscription']
        )
    
    async def get_user_with_full_data(self, user_id: int) -> Optional[User]:
        """
        Get user with all related data loaded.
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            User with all relationships loaded
        """
        user = await self.get_by_telegram_id(user_id)
        if not user:
            return None
        
        return await self.get_with_relationships(
            user.id,
            ['subscription', 'match_analyses', 'payments']
        )
    
    async def get_user_match_history(
        self,
        user_id: int,
        limit: int = 20
    ) -> List[MatchAnalysis]:
        """
        Get user's match analysis history.
        
        Args:
            user_id: Telegram user ID
            limit: Maximum number of matches
            
        Returns:
            List of match analyses
        """
        try:
            user = await self.get_by_telegram_id(user_id)
            if not user:
                return []
            
            async with self.get_session() as session:
                stmt = (
                    select(MatchAnalysis)
                    .where(MatchAnalysis.user_id == user.id)
                    .order_by(desc(MatchAnalysis.created_at))
                    .limit(limit)
                )
                
                result = await session.execute(stmt)
                return result.scalars().all()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_user_match_history: {e}")
            return []
    
    # Statistics and analytics
    async def get_user_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive user statistics.
        
        Returns:
            Dictionary with user statistics
        """
        try:
            async with self.get_session() as session:
                # Total users
                total_users = await self.count()
                
                # Users with FACEIT accounts
                users_with_faceit = await self.count(
                    filters={'faceit_player_id': {'not_null': True}}
                )
                
                # Active users (last 7 days)
                week_ago = datetime.now() - timedelta(days=7)
                active_users = await self.count(
                    filters={'last_active_at': {'gte': week_ago}}
                )
                
                # New users (last 24 hours)
                day_ago = datetime.now() - timedelta(days=1)
                new_users = await self.count(
                    filters={'created_at': {'gte': day_ago}}
                )
                
                # Language distribution
                lang_stmt = (
                    select(User.language, func.count(User.id).label('count'))
                    .group_by(User.language)
                    .order_by(desc('count'))
                )
                lang_result = await session.execute(lang_stmt)
                language_stats = {
                    row.language: row.count for row in lang_result
                }
                
                # Subscription tier distribution
                tier_stmt = (
                    select(UserSubscription.tier, func.count(UserSubscription.id).label('count'))
                    .group_by(UserSubscription.tier)
                )
                tier_result = await session.execute(tier_stmt)
                subscription_stats = {
                    row.tier.value: row.count for row in tier_result
                }
                
                return {
                    "total_users": total_users,
                    "users_with_faceit": users_with_faceit,
                    "active_users_7d": active_users,
                    "new_users_24h": new_users,
                    "faceit_link_rate": round((users_with_faceit / total_users * 100) if total_users > 0 else 0, 2),
                    "activity_rate": round((active_users / total_users * 100) if total_users > 0 else 0, 2),
                    "language_distribution": language_stats,
                    "subscription_distribution": subscription_stats,
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_user_stats: {e}")
            return {"error": str(e)}
    
    async def get_top_active_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get most active users by request count.
        
        Args:
            limit: Number of top users to return
            
        Returns:
            List of user activity data
        """
        try:
            async with self.get_session() as session:
                stmt = (
                    select(
                        User.user_id,
                        User.faceit_nickname,
                        User.total_requests,
                        User.last_active_at
                    )
                    .order_by(desc(User.total_requests))
                    .limit(limit)
                )
                
                result = await session.execute(stmt)
                return [
                    {
                        "user_id": row.user_id,
                        "nickname": row.faceit_nickname,
                        "total_requests": row.total_requests,
                        "last_active": row.last_active_at
                    }
                    for row in result
                ]
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_top_active_users: {e}")
            return []
    
    # Admin operations
    async def set_waiting_for_nickname(
        self,
        user_id: int,
        waiting: bool = True
    ) -> Optional[User]:
        """
        Set user's waiting_for_nickname flag.
        
        Args:
            user_id: Telegram user ID
            waiting: Whether user is waiting for nickname input
            
        Returns:
            Updated user or None if not found
        """
        try:
            async with self.get_session() as session:
                stmt = select(User).where(User.user_id == user_id)
                result = await session.execute(stmt)
                user = result.scalar_one_or_none()
                
                if not user:
                    return None
                
                user.waiting_for_nickname = waiting
                user.updated_at = datetime.now()
                
                await session.flush()
                await session.refresh(user)
                
                # Invalidate cache
                await self._invalidate_cache(f"users:telegram:{user_id}")
                
                return user
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in set_waiting_for_nickname: {e}")
            raise DatabaseOperationError(f"Failed to set waiting flag: {e}")
    
    async def bulk_update_activity(self, user_activities: List[Dict[str, Any]]) -> int:
        """
        Bulk update user activity data.
        
        Args:
            user_activities: List of user activity updates
            
        Returns:
            Number of updated users
        """
        updates = []
        for activity in user_activities:
            updates.append({
                'id': activity.get('user_id'),
                'last_active_at': activity.get('timestamp', datetime.now()),
                'total_requests': activity.get('requests', 0)
            })
        
        return await self.update_batch(updates)