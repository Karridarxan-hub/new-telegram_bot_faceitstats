"""
Player Statistics Repository implementation with caching and analytics.

Provides player statistics management functionality including:
- Player statistics CRUD operations and caching
- Performance analytics and trend analysis
- HLTV rating calculations and tracking
- Map-specific performance tracking
- Weapon preference analytics
- Clutch situation statistics
- Cache optimization with Redis integration
"""

import logging
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timedelta
import uuid

from sqlalchemy import select, and_, func, desc, text, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from database.models import PlayerStatsCache, User
from database.connection import DatabaseOperationError
from utils.redis_cache import player_cache, stats_cache
from .base import BaseRepository

logger = logging.getLogger(__name__)


class PlayerStatsCreateData:
    """Data class for creating player statistics."""
    def __init__(
        self,
        player_id: str,
        nickname: str,
        game: str = "cs2",
        user_id: Optional[uuid.UUID] = None,
        avatar: Optional[str] = None,
        country: Optional[str] = None,
        skill_level: Optional[int] = None,
        faceit_elo: Optional[int] = None,
        winrate: Optional[float] = None,
        avg_kd: Optional[float] = None,
        avg_adr: Optional[float] = None,
        hltv_rating: Optional[float] = None,
        recent_form: Optional[str] = None,
        danger_level: Optional[int] = None,
        player_role: Optional[str] = None,
        match_history_stats: Optional[Dict[str, Any]] = None,
        map_performance: Optional[Dict[str, Any]] = None,
        weapon_preferences: Optional[Dict[str, Any]] = None,
        clutch_stats: Optional[Dict[str, Any]] = None,
        cache_version: str = "1.0",
        expires_at: Optional[datetime] = None
    ):
        self.player_id = player_id
        self.nickname = nickname
        self.game = game
        self.user_id = user_id
        self.avatar = avatar
        self.country = country
        self.skill_level = skill_level
        self.faceit_elo = faceit_elo
        self.winrate = winrate
        self.avg_kd = avg_kd
        self.avg_adr = avg_adr
        self.hltv_rating = hltv_rating
        self.recent_form = recent_form
        self.danger_level = danger_level
        self.player_role = player_role
        self.match_history_stats = match_history_stats
        self.map_performance = map_performance
        self.weapon_preferences = weapon_preferences
        self.clutch_stats = clutch_stats
        self.cache_version = cache_version
        self.expires_at = expires_at or (datetime.now() + timedelta(minutes=30))


class StatsRepository(BaseRepository[PlayerStatsCache, PlayerStatsCreateData, Dict]):
    """
    Repository for PlayerStatsCache entity management.
    
    Provides comprehensive player statistics functionality with:
    - Player performance tracking and analytics
    - Statistics caching and optimization
    - Trend analysis and predictions
    - Map and weapon specific analytics
    - Team analysis and comparison
    - Performance-based rankings
    """
    
    def __init__(self):
        """Initialize stats repository with Redis cache."""
        super().__init__(PlayerStatsCache, stats_cache)
    
    # Core stats operations
    async def get_player_stats(
        self,
        player_id: str,
        game: str = "cs2"
    ) -> Optional[PlayerStatsCache]:
        """
        Get cached player statistics by player ID and game.
        
        Args:
            player_id: FACEIT player ID
            game: Game identifier
            
        Returns:
            PlayerStatsCache or None if not found or expired
        """
        cache_key = self._cache_key("player", player_id, game)
        
        # Try Redis cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            async with self.get_session() as session:
                stmt = (
                    select(PlayerStatsCache)
                    .where(
                        and_(
                            PlayerStatsCache.player_id == player_id,
                            PlayerStatsCache.game == game,
                            PlayerStatsCache.expires_at > datetime.now()
                        )
                    )
                )
                result = await session.execute(stmt)
                stats = result.scalar_one_or_none()
                
                # Cache in Redis if found
                if stats:
                    await self._set_cache(cache_key, stats, 300)
                
                return stats
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_player_stats: {e}")
            return None
    
    async def get_player_stats_by_nickname(
        self,
        nickname: str,
        game: str = "cs2"
    ) -> Optional[PlayerStatsCache]:
        """
        Get cached player statistics by nickname.
        
        Args:
            nickname: Player nickname
            game: Game identifier
            
        Returns:
            PlayerStatsCache or None if not found or expired
        """
        cache_key = self._cache_key("nickname", nickname.lower(), game)
        
        # Try Redis cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            async with self.get_session() as session:
                stmt = (
                    select(PlayerStatsCache)
                    .where(
                        and_(
                            func.lower(PlayerStatsCache.nickname) == nickname.lower(),
                            PlayerStatsCache.game == game,
                            PlayerStatsCache.expires_at > datetime.now()
                        )
                    )
                    .order_by(desc(PlayerStatsCache.updated_at))
                )
                result = await session.execute(stmt)
                stats = result.scalar_one_or_none()
                
                # Cache in Redis if found
                if stats:
                    await self._set_cache(cache_key, stats, 300)
                
                return stats
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_player_stats_by_nickname: {e}")
            return None
    
    async def cache_player_stats(
        self,
        player_id: str,
        nickname: str,
        stats_data: Dict[str, Any],
        game: str = "cs2",
        user_id: Optional[uuid.UUID] = None,
        ttl_minutes: int = 30
    ) -> PlayerStatsCache:
        """
        Cache player statistics with specified TTL.
        
        Args:
            player_id: FACEIT player ID
            nickname: Player nickname
            stats_data: Complete statistics data
            game: Game identifier
            user_id: Optional associated user ID
            ttl_minutes: Time to live in minutes
            
        Returns:
            Created or updated cache entry
        """
        try:
            async with self.get_session() as session:
                # Check if cache entry already exists
                existing = await self.get_player_stats(player_id, game)
                
                expires_at = datetime.now() + timedelta(minutes=ttl_minutes)
                
                if existing:
                    # Update existing entry
                    existing.nickname = nickname
                    existing.avatar = stats_data.get('avatar')
                    existing.country = stats_data.get('country')
                    existing.skill_level = stats_data.get('skill_level')
                    existing.faceit_elo = stats_data.get('faceit_elo')
                    existing.winrate = stats_data.get('winrate')
                    existing.avg_kd = stats_data.get('avg_kd')
                    existing.avg_adr = stats_data.get('avg_adr')
                    existing.hltv_rating = stats_data.get('hltv_rating')
                    existing.recent_form = stats_data.get('recent_form')
                    existing.danger_level = stats_data.get('danger_level')
                    existing.player_role = stats_data.get('player_role')
                    existing.match_history_stats = stats_data.get('match_history_stats')
                    existing.map_performance = stats_data.get('map_performance')
                    existing.weapon_preferences = stats_data.get('weapon_preferences')
                    existing.clutch_stats = stats_data.get('clutch_stats')
                    existing.expires_at = expires_at
                    existing.updated_at = datetime.now()
                    
                    await session.flush()
                    await session.refresh(existing)
                    
                    # Invalidate Redis cache
                    await self._invalidate_cache(f"player_stats_cache:*")
                    
                    return existing
                
                # Create new cache entry
                cache_entry = PlayerStatsCache(
                    player_id=player_id,
                    nickname=nickname,
                    game=game,
                    user_id=user_id,
                    avatar=stats_data.get('avatar'),
                    country=stats_data.get('country'),
                    skill_level=stats_data.get('skill_level'),
                    faceit_elo=stats_data.get('faceit_elo'),
                    winrate=stats_data.get('winrate'),
                    avg_kd=stats_data.get('avg_kd'),
                    avg_adr=stats_data.get('avg_adr'),
                    hltv_rating=stats_data.get('hltv_rating'),
                    recent_form=stats_data.get('recent_form'),
                    danger_level=stats_data.get('danger_level'),
                    player_role=stats_data.get('player_role'),
                    match_history_stats=stats_data.get('match_history_stats'),
                    map_performance=stats_data.get('map_performance'),
                    weapon_preferences=stats_data.get('weapon_preferences'),
                    clutch_stats=stats_data.get('clutch_stats'),
                    expires_at=expires_at,
                    created_at=datetime.now()
                )
                
                session.add(cache_entry)
                await session.flush()
                await session.refresh(cache_entry)
                
                logger.info(f"Cached player stats for {nickname} (ID: {player_id}, TTL: {ttl_minutes}m)")
                return cache_entry
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in cache_player_stats: {e}")
            raise DatabaseOperationError(f"Failed to cache player stats: {e}")
    
    # Batch operations
    async def cache_multiple_players(
        self,
        players_data: List[Dict[str, Any]],
        game: str = "cs2",
        ttl_minutes: int = 30
    ) -> List[PlayerStatsCache]:
        """
        Cache statistics for multiple players in batch.
        
        Args:
            players_data: List of player statistics data
            game: Game identifier
            ttl_minutes: Time to live in minutes
            
        Returns:
            List of cached player statistics
        """
        try:
            async with self.get_session() as session:
                cached_players = []
                expires_at = datetime.now() + timedelta(minutes=ttl_minutes)
                
                for player_data in players_data:
                    player_id = player_data.get('player_id')
                    nickname = player_data.get('nickname')
                    
                    if not player_id or not nickname:
                        continue
                    
                    # Check if exists
                    existing_stmt = select(PlayerStatsCache).where(
                        and_(
                            PlayerStatsCache.player_id == player_id,
                            PlayerStatsCache.game == game
                        )
                    )
                    existing_result = await session.execute(existing_stmt)
                    existing = existing_result.scalar_one_or_none()
                    
                    if existing:
                        # Update existing
                        for key, value in player_data.items():
                            if hasattr(existing, key) and key not in ['player_id', 'game']:
                                setattr(existing, key, value)
                        existing.expires_at = expires_at
                        existing.updated_at = datetime.now()
                        cached_players.append(existing)
                    else:
                        # Create new
                        cache_entry = PlayerStatsCache(
                            **player_data,
                            game=game,
                            expires_at=expires_at,
                            created_at=datetime.now()
                        )
                        session.add(cache_entry)
                        cached_players.append(cache_entry)
                
                await session.flush()
                
                # Refresh all objects
                for player in cached_players:
                    await session.refresh(player)
                
                # Invalidate Redis cache
                await self._invalidate_cache(f"player_stats_cache:*")
                
                logger.info(f"Cached stats for {len(cached_players)} players")
                return cached_players
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in cache_multiple_players: {e}")
            return []
    
    async def get_team_stats(
        self,
        player_ids: List[str],
        game: str = "cs2"
    ) -> List[PlayerStatsCache]:
        """
        Get statistics for multiple players (team analysis).
        
        Args:
            player_ids: List of FACEIT player IDs
            game: Game identifier
            
        Returns:
            List of player statistics
        """
        try:
            async with self.get_session() as session:
                stmt = (
                    select(PlayerStatsCache)
                    .where(
                        and_(
                            PlayerStatsCache.player_id.in_(player_ids),
                            PlayerStatsCache.game == game,
                            PlayerStatsCache.expires_at > datetime.now()
                        )
                    )
                )
                result = await session.execute(stmt)
                return result.scalars().all()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_team_stats: {e}")
            return []
    
    # Analytics and rankings
    async def get_top_players_by_rating(
        self,
        game: str = "cs2",
        limit: int = 50,
        min_matches: int = 10
    ) -> List[PlayerStatsCache]:
        """
        Get top players by HLTV rating.
        
        Args:
            game: Game identifier
            limit: Maximum number of players
            min_matches: Minimum number of matches required
            
        Returns:
            List of top-rated players
        """
        try:
            async with self.get_session() as session:
                stmt = (
                    select(PlayerStatsCache)
                    .where(
                        and_(
                            PlayerStatsCache.game == game,
                            PlayerStatsCache.expires_at > datetime.now(),
                            PlayerStatsCache.hltv_rating.is_not(None),
                            PlayerStatsCache.hltv_rating > 0
                        )
                    )
                    .order_by(desc(PlayerStatsCache.hltv_rating))
                    .limit(limit)
                )
                
                # Add filter for minimum matches if match_history_stats is available
                if min_matches > 0:
                    stmt = stmt.where(
                        or_(
                            PlayerStatsCache.match_history_stats.is_(None),
                            func.cast(
                                PlayerStatsCache.match_history_stats['total_matches'].astext,
                                func.INTEGER
                            ) >= min_matches
                        )
                    )
                
                result = await session.execute(stmt)
                return result.scalars().all()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_top_players_by_rating: {e}")
            return []
    
    async def get_players_by_danger_level(
        self,
        danger_level: int,
        game: str = "cs2",
        limit: int = 20
    ) -> List[PlayerStatsCache]:
        """
        Get players with specific danger level.
        
        Args:
            danger_level: Danger level (1-5)
            game: Game identifier
            limit: Maximum number of players
            
        Returns:
            List of players with specified danger level
        """
        return await self.get_all(
            limit=limit,
            filters={
                'game': game,
                'danger_level': danger_level,
                'expires_at': {'gte': datetime.now()}
            },
            order_by='hltv_rating',
            order_desc=True
        )
    
    async def search_players_by_skill_range(
        self,
        min_skill_level: int,
        max_skill_level: int,
        game: str = "cs2",
        limit: int = 50
    ) -> List[PlayerStatsCache]:
        """
        Search players within skill level range.
        
        Args:
            min_skill_level: Minimum skill level
            max_skill_level: Maximum skill level
            game: Game identifier
            limit: Maximum number of players
            
        Returns:
            List of players within skill range
        """
        try:
            async with self.get_session() as session:
                stmt = (
                    select(PlayerStatsCache)
                    .where(
                        and_(
                            PlayerStatsCache.game == game,
                            PlayerStatsCache.expires_at > datetime.now(),
                            PlayerStatsCache.skill_level >= min_skill_level,
                            PlayerStatsCache.skill_level <= max_skill_level
                        )
                    )
                    .order_by(desc(PlayerStatsCache.skill_level), desc(PlayerStatsCache.faceit_elo))
                    .limit(limit)
                )
                
                result = await session.execute(stmt)
                return result.scalars().all()
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in search_players_by_skill_range: {e}")
            return []
    
    # Map-specific analytics
    async def get_map_performance_stats(
        self,
        map_name: str,
        game: str = "cs2",
        min_matches: int = 5
    ) -> Dict[str, Any]:
        """
        Get aggregated performance statistics for specific map.
        
        Args:
            map_name: Map name
            game: Game identifier
            min_matches: Minimum matches on map required
            
        Returns:
            Dictionary with map performance statistics
        """
        try:
            async with self.get_session() as session:
                # Find players with performance data on this map
                stmt = (
                    select(PlayerStatsCache)
                    .where(
                        and_(
                            PlayerStatsCache.game == game,
                            PlayerStatsCache.expires_at > datetime.now(),
                            PlayerStatsCache.map_performance.is_not(None)
                        )
                    )
                )
                
                result = await session.execute(stmt)
                players = result.scalars().all()
                
                map_stats = []
                for player in players:
                    if player.map_performance and map_name in player.map_performance:
                        map_data = player.map_performance[map_name]
                        matches = map_data.get('matches', 0)
                        
                        if matches >= min_matches:
                            map_stats.append({
                                'player_id': player.player_id,
                                'nickname': player.nickname,
                                'matches': matches,
                                'winrate': map_data.get('winrate', 0),
                                'avg_rating': map_data.get('avg_rating', 0),
                                'avg_kd': map_data.get('avg_kd', 0)
                            })
                
                if not map_stats:
                    return {"map_name": map_name, "stats": [], "aggregated": {}}
                
                # Calculate aggregated statistics
                total_players = len(map_stats)
                avg_winrate = sum(s['winrate'] for s in map_stats) / total_players
                avg_rating = sum(s['avg_rating'] for s in map_stats) / total_players
                avg_kd = sum(s['avg_kd'] for s in map_stats) / total_players
                
                # Top performers
                top_performers = sorted(map_stats, key=lambda x: x['avg_rating'], reverse=True)[:10]
                
                return {
                    "map_name": map_name,
                    "total_players": total_players,
                    "aggregated": {
                        "average_winrate": round(avg_winrate, 2),
                        "average_rating": round(avg_rating, 3),
                        "average_kd": round(avg_kd, 2)
                    },
                    "top_performers": top_performers,
                    "stats": map_stats[:50]  # Limit for performance
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_map_performance_stats: {e}")
            return {"error": str(e)}
    
    # Trend analysis
    async def analyze_player_trends(
        self,
        player_id: str,
        game: str = "cs2",
        days_back: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze player performance trends over time.
        
        Args:
            player_id: FACEIT player ID
            game: Game identifier
            days_back: Number of days to analyze
            
        Returns:
            Dictionary with trend analysis
        """
        try:
            since_date = datetime.now() - timedelta(days=days_back)
            
            async with self.get_session() as session:
                # Get historical cache entries for this player
                stmt = (
                    select(PlayerStatsCache)
                    .where(
                        and_(
                            PlayerStatsCache.player_id == player_id,
                            PlayerStatsCache.game == game,
                            PlayerStatsCache.updated_at >= since_date
                        )
                    )
                    .order_by(PlayerStatsCache.updated_at)
                )
                
                result = await session.execute(stmt)
                historical_stats = result.scalars().all()
                
                if len(historical_stats) < 2:
                    return {"error": "Insufficient historical data"}
                
                # Calculate trends
                first_stats = historical_stats[0]
                latest_stats = historical_stats[-1]
                
                trends = {}
                
                # Numeric fields to analyze
                numeric_fields = [
                    'skill_level', 'faceit_elo', 'winrate', 'avg_kd', 
                    'avg_adr', 'hltv_rating', 'danger_level'
                ]
                
                for field in numeric_fields:
                    first_value = getattr(first_stats, field)
                    latest_value = getattr(latest_stats, field)
                    
                    if first_value is not None and latest_value is not None:
                        change = latest_value - first_value
                        change_percent = (change / first_value * 100) if first_value != 0 else 0
                        
                        trends[field] = {
                            "first_value": first_value,
                            "latest_value": latest_value,
                            "change": round(change, 3),
                            "change_percent": round(change_percent, 2),
                            "direction": "up" if change > 0 else "down" if change < 0 else "stable"
                        }
                
                # Analyze recent form changes
                recent_forms = [s.recent_form for s in historical_stats if s.recent_form]
                form_trend = "unknown"
                if len(recent_forms) >= 2:
                    latest_form = recent_forms[-1]
                    win_count = latest_form.count('W') if latest_form else 0
                    total_matches = len(latest_form) if latest_form else 0
                    current_winrate = (win_count / total_matches) if total_matches > 0 else 0
                    
                    if current_winrate >= 0.6:
                        form_trend = "good"
                    elif current_winrate >= 0.4:
                        form_trend = "average"
                    else:
                        form_trend = "poor"
                
                return {
                    "player_id": player_id,
                    "analysis_period_days": days_back,
                    "data_points": len(historical_stats),
                    "trends": trends,
                    "form_trend": form_trend,
                    "latest_stats": {
                        "nickname": latest_stats.nickname,
                        "skill_level": latest_stats.skill_level,
                        "faceit_elo": latest_stats.faceit_elo,
                        "hltv_rating": latest_stats.hltv_rating,
                        "danger_level": latest_stats.danger_level
                    }
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in analyze_player_trends: {e}")
            return {"error": str(e)}
    
    # Cache management
    async def cleanup_expired_stats(self) -> int:
        """
        Remove expired player statistics cache entries.
        
        Returns:
            Number of removed entries
        """
        try:
            async with self.get_session() as session:
                stmt = select(PlayerStatsCache.id).where(
                    PlayerStatsCache.expires_at < datetime.now()
                )
                result = await session.execute(stmt)
                expired_ids = [row.id for row in result]
                
                if expired_ids:
                    deleted_count = await self.delete_batch(expired_ids)
                    logger.info(f"Cleaned up {deleted_count} expired player stats")
                    return deleted_count
                
                return 0
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in cleanup_expired_stats: {e}")
            return 0
    
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive cache usage statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            async with self.get_session() as session:
                # Total cached players
                total_cached = await self.count()
                
                # Active (non-expired) cached players
                active_cached = await self.count(
                    filters={'expires_at': {'gte': datetime.now()}}
                )
                
                # Game distribution
                game_stmt = (
                    select(PlayerStatsCache.game, func.count(PlayerStatsCache.id).label('count'))
                    .where(PlayerStatsCache.expires_at > datetime.now())
                    .group_by(PlayerStatsCache.game)
                )
                game_result = await session.execute(game_stmt)
                game_distribution = {row.game: row.count for row in game_result}
                
                # Skill level distribution
                skill_stmt = (
                    select(PlayerStatsCache.skill_level, func.count(PlayerStatsCache.id).label('count'))
                    .where(
                        and_(
                            PlayerStatsCache.expires_at > datetime.now(),
                            PlayerStatsCache.skill_level.is_not(None)
                        )
                    )
                    .group_by(PlayerStatsCache.skill_level)
                    .order_by(PlayerStatsCache.skill_level)
                )
                skill_result = await session.execute(skill_stmt)
                skill_distribution = {f"level_{row.skill_level}": row.count for row in skill_result}
                
                # Cache hit statistics (approximate based on creation vs update times)
                recently_created_stmt = select(func.count(PlayerStatsCache.id)).where(
                    and_(
                        PlayerStatsCache.expires_at > datetime.now(),
                        PlayerStatsCache.created_at >= datetime.now() - timedelta(hours=1)
                    )
                )
                recently_created_result = await session.execute(recently_created_stmt)
                recent_cache_misses = recently_created_result.scalar() or 0
                
                return {
                    "total_cached_players": total_cached,
                    "active_cached_players": active_cached,
                    "expired_cached_players": total_cached - active_cached,
                    "game_distribution": game_distribution,
                    "skill_level_distribution": skill_distribution,
                    "cache_performance": {
                        "recent_cache_misses_1h": recent_cache_misses,
                        "cache_utilization": round((active_cached / total_cached * 100) if total_cached > 0 else 0, 2)
                    }
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_cache_statistics: {e}")
            return {"error": str(e)}