"""
Match Repository implementation with analysis and caching.

Provides match management functionality including:
- Match analysis CRUD operations
- Match data caching and optimization
- Analysis history tracking
- Performance metrics and statistics
- Cache management with Redis integration
"""

import logging
from typing import Optional, List, Dict, Any, Union, Tuple
from datetime import datetime, timedelta
import uuid

from sqlalchemy import select, and_, func, desc, text, or_
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, IntegrityError

from database.models import (
    MatchAnalysis, MatchCache, User, MatchStatus
)
from database.connection import DatabaseOperationError
from utils.redis_cache import match_cache, stats_cache
from .base import BaseRepository

logger = logging.getLogger(__name__)


class MatchAnalysisCreateData:
    """Data class for creating match analyses."""
    def __init__(
        self,
        user_id: uuid.UUID,
        match_id: str,
        match_url: Optional[str] = None,
        game: str = "cs2",
        region: Optional[str] = None,
        map_name: Optional[str] = None,
        competition_name: Optional[str] = None,
        competition_type: Optional[str] = None,
        team1_analysis: Optional[Dict[str, Any]] = None,
        team2_analysis: Optional[Dict[str, Any]] = None,
        match_prediction: Optional[Dict[str, Any]] = None,
        processing_time_ms: Optional[int] = None,
        cached_data_used: bool = False
    ):
        self.user_id = user_id
        self.match_id = match_id
        self.match_url = match_url
        self.game = game
        self.region = region
        self.map_name = map_name
        self.competition_name = competition_name
        self.competition_type = competition_type
        self.team1_analysis = team1_analysis
        self.team2_analysis = team2_analysis
        self.match_prediction = match_prediction
        self.processing_time_ms = processing_time_ms
        self.cached_data_used = cached_data_used


class MatchCacheCreateData:
    """Data class for creating match cache entries."""
    def __init__(
        self,
        match_id: str,
        match_data: Dict[str, Any],
        match_stats: Optional[Dict[str, Any]] = None,
        cache_version: str = "1.0",
        data_source: str = "faceit_api",
        expires_at: Optional[datetime] = None
    ):
        self.match_id = match_id
        self.match_data = match_data
        self.match_stats = match_stats
        self.cache_version = cache_version
        self.data_source = data_source
        self.expires_at = expires_at or (datetime.now() + timedelta(minutes=30))


class MatchRepository(BaseRepository[MatchAnalysis, MatchAnalysisCreateData, Dict]):
    """
    Repository for MatchAnalysis entity management.
    
    Provides comprehensive match analysis functionality with:
    - Match analysis tracking and history
    - Performance optimization with caching
    - Analysis statistics and metrics
    - Match status updates and monitoring
    - Redis cache integration for performance
    """
    
    def __init__(self):
        """Initialize match repository with Redis cache."""
        super().__init__(MatchAnalysis, stats_cache)
    
    # Core match analysis operations
    async def get_by_match_id(
        self,
        match_id: str,
        user_id: Optional[uuid.UUID] = None
    ) -> Optional[MatchAnalysis]:
        """
        Get match analysis by match ID, optionally filtered by user.
        
        Args:
            match_id: FACEIT match ID
            user_id: Optional user UUID to filter by
            
        Returns:
            MatchAnalysis or None if not found
        """
        cache_key = self._cache_key("match", match_id, user_id or "all")
        
        # Try cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            async with self.get_session() as session:
                stmt = select(MatchAnalysis).where(MatchAnalysis.match_id == match_id)
                
                if user_id:
                    stmt = stmt.where(MatchAnalysis.user_id == user_id)
                
                # Get most recent analysis for this match
                stmt = stmt.order_by(desc(MatchAnalysis.created_at))
                
                result = await session.execute(stmt)
                analysis = result.scalar_one_or_none()
                
                # Cache result
                if analysis:
                    await self._set_cache(cache_key, analysis, 600)
                
                return analysis
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_by_match_id: {e}")
            raise DatabaseOperationError(f"Failed to get match analysis: {e}")
    
    async def create_analysis(
        self,
        user_id: uuid.UUID,
        match_id: str,
        analysis_data: Dict[str, Any],
        processing_time_ms: Optional[int] = None
    ) -> MatchAnalysis:
        """
        Create new match analysis.
        
        Args:
            user_id: User UUID who requested the analysis
            match_id: FACEIT match ID
            analysis_data: Complete analysis data
            processing_time_ms: Processing time in milliseconds
            
        Returns:
            Created match analysis
        """
        try:
            async with self.get_session() as session:
                # Check if analysis already exists for this user and match
                existing = await self.get_by_match_id(match_id, user_id)
                if existing:
                    logger.info(f"Match analysis already exists: {match_id} for user {user_id}")
                    return existing
                
                # Extract data from analysis_data
                match_info = analysis_data.get('match_info', {})
                team1_data = analysis_data.get('team1_analysis', {})
                team2_data = analysis_data.get('team2_analysis', {})
                prediction = analysis_data.get('prediction', {})
                
                analysis = MatchAnalysis(
                    user_id=user_id,
                    match_id=match_id,
                    match_url=analysis_data.get('match_url'),
                    game=match_info.get('game', 'cs2'),
                    region=match_info.get('region'),
                    map_name=match_info.get('map'),
                    status=MatchStatus(match_info.get('status', 'scheduled')),
                    competition_name=match_info.get('competition_name'),
                    competition_type=match_info.get('competition_type'),
                    team1_analysis=team1_data,
                    team2_analysis=team2_data,
                    match_prediction=prediction,
                    processing_time_ms=processing_time_ms,
                    cached_data_used=analysis_data.get('cached_data_used', False),
                    configured_at=self._parse_datetime(match_info.get('configured_at')),
                    started_at=self._parse_datetime(match_info.get('started_at')),
                    finished_at=self._parse_datetime(match_info.get('finished_at')),
                    created_at=datetime.now()
                )
                
                session.add(analysis)
                await session.flush()
                await session.refresh(analysis)
                
                # Invalidate caches
                await self._invalidate_cache("match_analyses:*")
                
                logger.info(f"Created match analysis {analysis.id} for match {match_id}")
                return analysis
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in create_analysis: {e}")
            raise DatabaseOperationError(f"Failed to create match analysis: {e}")
    
    async def update_match_status(
        self,
        match_id: str,
        status: MatchStatus,
        finished_at: Optional[datetime] = None
    ) -> List[MatchAnalysis]:
        """
        Update match status for all analyses of this match.
        
        Args:
            match_id: FACEIT match ID
            status: New match status
            finished_at: Optional finish time
            
        Returns:
            List of updated match analyses
        """
        try:
            async with self.get_session() as session:
                stmt = select(MatchAnalysis).where(MatchAnalysis.match_id == match_id)
                result = await session.execute(stmt)
                analyses = result.scalars().all()
                
                updated_analyses = []
                for analysis in analyses:
                    analysis.status = status
                    analysis.updated_at = datetime.now()
                    
                    if finished_at:
                        analysis.finished_at = finished_at
                    
                    await session.flush()
                    updated_analyses.append(analysis)
                
                if updated_analyses:
                    # Invalidate caches
                    await self._invalidate_cache("match_analyses:*")
                    logger.info(f"Updated status to {status} for {len(updated_analyses)} analyses of match {match_id}")
                
                return updated_analyses
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in update_match_status: {e}")
            raise DatabaseOperationError(f"Failed to update match status: {e}")
    
    # User analysis history
    async def get_user_analyses(
        self,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
        status: Optional[MatchStatus] = None,
        game: Optional[str] = None
    ) -> List[MatchAnalysis]:
        """
        Get user's match analysis history.
        
        Args:
            user_id: User UUID
            limit: Maximum number of results
            offset: Number of results to skip
            status: Optional match status filter
            game: Optional game filter
            
        Returns:
            List of match analyses
        """
        filters = {'user_id': user_id}
        
        if status:
            filters['status'] = status
        if game:
            filters['game'] = game
        
        return await self.get_all(
            skip=offset,
            limit=limit,
            filters=filters,
            order_by='created_at',
            order_desc=True
        )
    
    async def get_user_recent_analyses(
        self,
        user_id: uuid.UUID,
        hours: int = 24
    ) -> List[MatchAnalysis]:
        """
        Get user's recent analyses within specified hours.
        
        Args:
            user_id: User UUID
            hours: Number of hours to look back
            
        Returns:
            List of recent analyses
        """
        since_time = datetime.now() - timedelta(hours=hours)
        
        return await self.get_all(
            filters={
                'user_id': user_id,
                'created_at': {'gte': since_time}
            },
            order_by='created_at',
            order_desc=True
        )
    
    # Analysis statistics
    async def get_match_analysis_stats(
        self,
        user_id: Optional[uuid.UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get comprehensive match analysis statistics.
        
        Args:
            user_id: Optional user UUID to filter by
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Dictionary with analysis statistics
        """
        try:
            async with self.get_session() as session:
                # Base query
                base_stmt = select(MatchAnalysis)
                
                if user_id:
                    base_stmt = base_stmt.where(MatchAnalysis.user_id == user_id)
                if start_date:
                    base_stmt = base_stmt.where(MatchAnalysis.created_at >= start_date)
                if end_date:
                    base_stmt = base_stmt.where(MatchAnalysis.created_at <= end_date)
                
                # Total analyses
                total_stmt = select(func.count()).select_from(base_stmt.subquery())
                total_result = await session.execute(total_stmt)
                total_analyses = total_result.scalar() or 0
                
                # Status distribution
                status_stmt = (
                    select(MatchAnalysis.status, func.count(MatchAnalysis.id).label('count'))
                    .select_from(base_stmt.subquery())
                    .group_by(MatchAnalysis.status)
                )
                status_result = await session.execute(status_stmt)
                status_distribution = {row.status.value: row.count for row in status_result}
                
                # Game distribution
                game_stmt = (
                    select(MatchAnalysis.game, func.count(MatchAnalysis.id).label('count'))
                    .select_from(base_stmt.subquery())
                    .group_by(MatchAnalysis.game)
                )
                game_result = await session.execute(game_stmt)
                game_distribution = {row.game: row.count for row in game_result}
                
                # Processing time statistics
                processing_time_stmt = (
                    select(
                        func.avg(MatchAnalysis.processing_time_ms).label('avg_time'),
                        func.min(MatchAnalysis.processing_time_ms).label('min_time'),
                        func.max(MatchAnalysis.processing_time_ms).label('max_time')
                    )
                    .select_from(base_stmt.subquery())
                    .where(MatchAnalysis.processing_time_ms.is_not(None))
                )
                processing_result = await session.execute(processing_time_stmt)
                processing_stats = processing_result.first()
                
                # Cache usage
                cache_stmt = (
                    select(
                        func.sum(func.cast(MatchAnalysis.cached_data_used, func.INTEGER)).label('cached_count')
                    )
                    .select_from(base_stmt.subquery())
                )
                cache_result = await session.execute(cache_stmt)
                cached_analyses = cache_result.scalar() or 0
                
                return {
                    "total_analyses": total_analyses,
                    "status_distribution": status_distribution,
                    "game_distribution": game_distribution,
                    "cache_usage": {
                        "cached_analyses": cached_analyses,
                        "cache_hit_rate": round((cached_analyses / total_analyses * 100) if total_analyses > 0 else 0, 2)
                    },
                    "processing_times": {
                        "average_ms": round(processing_stats.avg_time or 0, 2),
                        "minimum_ms": processing_stats.min_time or 0,
                        "maximum_ms": processing_stats.max_time or 0
                    },
                    "period": {
                        "start": start_date.isoformat() if start_date else None,
                        "end": end_date.isoformat() if end_date else None
                    }
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_match_analysis_stats: {e}")
            return {"error": str(e)}
    
    async def get_popular_matches(
        self,
        limit: int = 10,
        hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Get most analyzed matches in recent period.
        
        Args:
            limit: Maximum number of matches to return
            hours: Time period in hours
            
        Returns:
            List of popular match data
        """
        try:
            since_time = datetime.now() - timedelta(hours=hours)
            
            async with self.get_session() as session:
                stmt = (
                    select(
                        MatchAnalysis.match_id,
                        MatchAnalysis.competition_name,
                        MatchAnalysis.map_name,
                        MatchAnalysis.game,
                        func.count(MatchAnalysis.id).label('analysis_count'),
                        func.max(MatchAnalysis.created_at).label('latest_analysis')
                    )
                    .where(MatchAnalysis.created_at >= since_time)
                    .group_by(
                        MatchAnalysis.match_id,
                        MatchAnalysis.competition_name,
                        MatchAnalysis.map_name,
                        MatchAnalysis.game
                    )
                    .order_by(desc('analysis_count'))
                    .limit(limit)
                )
                
                result = await session.execute(stmt)
                
                return [
                    {
                        "match_id": row.match_id,
                        "competition_name": row.competition_name,
                        "map_name": row.map_name,
                        "game": row.game,
                        "analysis_count": row.analysis_count,
                        "latest_analysis": row.latest_analysis
                    }
                    for row in result
                ]
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_popular_matches: {e}")
            return []
    
    # Performance optimization
    async def cleanup_old_analyses(self, days_old: int = 30) -> int:
        """
        Clean up old match analyses to free up space.
        
        Args:
            days_old: Age threshold in days
            
        Returns:
            Number of deleted analyses
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            
            async with self.get_session() as session:
                # Only delete analyses for completed matches older than threshold
                stmt = select(MatchAnalysis.id).where(
                    and_(
                        MatchAnalysis.created_at < cutoff_date,
                        MatchAnalysis.status.in_([MatchStatus.FINISHED, MatchStatus.CANCELLED])
                    )
                )
                result = await session.execute(stmt)
                old_ids = [row.id for row in result]
                
                if old_ids:
                    deleted_count = await self.delete_batch(old_ids)
                    logger.info(f"Cleaned up {deleted_count} old match analyses")
                    return deleted_count
                
                return 0
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in cleanup_old_analyses: {e}")
            return 0
    
    # Helper methods
    def _parse_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Parse datetime string to datetime object."""
        if not dt_str:
            return None
        
        try:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None


class MatchCacheRepository(BaseRepository[MatchCache, MatchCacheCreateData, Dict]):
    """
    Repository for MatchCache entity management.
    
    Provides match data caching functionality with:
    - FACEIT API response caching
    - Cache expiration and cleanup
    - Access tracking and statistics
    - Performance optimization
    """
    
    def __init__(self):
        """Initialize match cache repository with Redis cache."""
        super().__init__(MatchCache, match_cache)
    
    # Cache operations
    async def get_cached_match(self, match_id: str) -> Optional[MatchCache]:
        """
        Get cached match data by match ID.
        
        Args:
            match_id: FACEIT match ID
            
        Returns:
            MatchCache or None if not found or expired
        """
        cache_key = self._cache_key("data", match_id)
        
        # Try Redis cache first
        cached_result = await self._get_from_cache(cache_key)
        if cached_result is not None:
            return cached_result
        
        try:
            async with self.get_session() as session:
                stmt = (
                    select(MatchCache)
                    .where(
                        and_(
                            MatchCache.match_id == match_id,
                            MatchCache.expires_at > datetime.now()
                        )
                    )
                )
                result = await session.execute(stmt)
                match_cache_entry = result.scalar_one_or_none()
                
                if match_cache_entry:
                    # Update access tracking
                    match_cache_entry.access_count += 1
                    match_cache_entry.last_accessed_at = datetime.now()
                    await session.flush()
                    
                    # Cache in Redis
                    await self._set_cache(cache_key, match_cache_entry, 300)
                
                return match_cache_entry
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_cached_match: {e}")
            return None
    
    async def cache_match_data(
        self,
        match_id: str,
        match_data: Dict[str, Any],
        match_stats: Optional[Dict[str, Any]] = None,
        ttl_minutes: int = 30
    ) -> MatchCache:
        """
        Cache match data with specified TTL.
        
        Args:
            match_id: FACEIT match ID
            match_data: Match data from API
            match_stats: Optional match statistics
            ttl_minutes: Time to live in minutes
            
        Returns:
            Created cache entry
        """
        try:
            async with self.get_session() as session:
                # Check if cache entry already exists
                existing = await self.get_cached_match(match_id)
                if existing:
                    # Update existing entry
                    existing.match_data = match_data
                    existing.match_stats = match_stats
                    existing.expires_at = datetime.now() + timedelta(minutes=ttl_minutes)
                    existing.updated_at = datetime.now()
                    
                    await session.flush()
                    await session.refresh(existing)
                    
                    # Invalidate Redis cache
                    await self._invalidate_cache(f"match_cache:data:{match_id}")
                    
                    return existing
                
                # Create new cache entry
                cache_entry = MatchCache(
                    match_id=match_id,
                    match_data=match_data,
                    match_stats=match_stats,
                    expires_at=datetime.now() + timedelta(minutes=ttl_minutes),
                    created_at=datetime.now()
                )
                
                session.add(cache_entry)
                await session.flush()
                await session.refresh(cache_entry)
                
                logger.info(f"Cached match data for {match_id} (TTL: {ttl_minutes}m)")
                return cache_entry
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in cache_match_data: {e}")
            raise DatabaseOperationError(f"Failed to cache match data: {e}")
    
    async def cleanup_expired_cache(self) -> int:
        """
        Remove expired cache entries.
        
        Returns:
            Number of removed entries
        """
        try:
            async with self.get_session() as session:
                stmt = select(MatchCache.id).where(MatchCache.expires_at < datetime.now())
                result = await session.execute(stmt)
                expired_ids = [row.id for row in result]
                
                if expired_ids:
                    deleted_count = await self.delete_batch(expired_ids)
                    logger.info(f"Cleaned up {deleted_count} expired cache entries")
                    return deleted_count
                
                return 0
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in cleanup_expired_cache: {e}")
            return 0
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache usage statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            async with self.get_session() as session:
                # Total cache entries
                total_entries = await self.count()
                
                # Active (non-expired) entries
                active_entries = await self.count(
                    filters={'expires_at': {'gte': datetime.now()}}
                )
                
                # Most accessed entries
                most_accessed_stmt = (
                    select(MatchCache.match_id, MatchCache.access_count)
                    .order_by(desc(MatchCache.access_count))
                    .limit(10)
                )
                most_accessed_result = await session.execute(most_accessed_stmt)
                most_accessed = [
                    {"match_id": row.match_id, "access_count": row.access_count}
                    for row in most_accessed_result
                ]
                
                # Total access count
                total_access_stmt = select(func.sum(MatchCache.access_count))
                total_access_result = await session.execute(total_access_stmt)
                total_accesses = total_access_result.scalar() or 0
                
                return {
                    "total_entries": total_entries,
                    "active_entries": active_entries,
                    "expired_entries": total_entries - active_entries,
                    "total_accesses": total_accesses,
                    "average_accesses": round(total_accesses / total_entries, 2) if total_entries > 0 else 0,
                    "most_accessed": most_accessed,
                    "cache_hit_rate": round((active_entries / total_entries * 100) if total_entries > 0 else 0, 2)
                }
                
        except SQLAlchemyError as e:
            logger.error(f"Database error in get_cache_stats: {e}")
            return {"error": str(e)}