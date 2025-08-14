"""
DEPRECATED: Legacy cache system - now uses Redis
This file serves as a compatibility bridge during migration
"""

import logging
from typing import Dict, Any
from config.settings import settings
from utils.redis_cache import (
    player_cache,
    match_cache, 
    stats_cache,
    get_all_cache_stats,
    clear_all_caches as redis_clear_all_caches,
    cache_player_data,
    cache_match_data,
    cache_stats_data
)

logger = logging.getLogger(__name__)


class CachedFaceitAPI:
    """Redis-based FACEIT API wrapper with caching."""
    
    def __init__(self, faceit_api):
        self.api = faceit_api
    
    @cache_player_data(ttl=300)
    async def get_player_by_id(self, player_id: str):
        """Get player with Redis caching."""
        return await self.api.get_player_by_id(player_id)
    
    @cache_stats_data(ttl=600)
    async def get_player_stats(self, player_id: str, game: str = "cs2"):
        """Get player stats with Redis caching."""
        return await self.api.get_player_stats(player_id, game)
    
    @cache_match_data(ttl=120)
    async def get_match_details(self, match_id: str):
        """Get match details with Redis caching."""
        return await self.api.get_match_details(match_id)
    
    @cache_stats_data(ttl=300)
    async def get_player_matches(self, player_id: str, limit: int = 20, offset: int = 0, game: str = "cs2"):
        """Get player matches with Redis caching."""
        return await self.api.get_player_matches(player_id, limit, offset, game)
    
    @cache_match_data(ttl=180)
    async def get_match_stats(self, match_id: str):
        """Get match stats with Redis caching."""
        return await self.api.get_match_stats(match_id)
    
    async def get_matches_with_stats(self, player_id: str, limit: int = 20, game: str = "cs2"):
        """Get matches with stats (optimized with Redis caching)."""
        import asyncio
        
        # Get matches using cached method
        matches = await self.get_player_matches(player_id, limit, 0, game)
        
        # Parallel stats gathering with Redis caching
        match_stats_tasks = []
        for match in matches:
            if match.status.upper() == "FINISHED":
                task = self.get_match_stats(match.match_id)
                match_stats_tasks.append(task)
            else:
                match_stats_tasks.append(asyncio.create_task(self._return_none()))
        
        # Limit concurrent requests
        semaphore = asyncio.Semaphore(8)
        
        async def limited_task(task):
            async with semaphore:
                return await task
        
        stats_results = await asyncio.gather(
            *[limited_task(task) for task in match_stats_tasks],
            return_exceptions=True
        )
        
        # Combine results
        matches_with_stats = []
        for i, match in enumerate(matches):
            stats = stats_results[i] if i < len(stats_results) else None
            if isinstance(stats, Exception):
                stats = None
            matches_with_stats.append((match, stats))
        
        return matches_with_stats
    
    async def _return_none(self):
        """Helper function to return None."""
        return None
    
    # Methods without caching for critical operations
    async def search_player(self, nickname: str):
        """Search player (no caching - can be inaccurate)."""
        return await self.api.search_player(nickname)
    
    async def check_player_new_matches(self, player_id: str, last_checked_match_id: str = None):
        """Check new matches (no caching - needs freshness)."""
        return await self.api.check_player_new_matches(player_id, last_checked_match_id)


async def get_cache_stats() -> Dict[str, Any]:
    """Get statistics from all Redis caches."""
    stats = await get_all_cache_stats()
    
    # Transform to legacy format for compatibility  
    player_stats = stats["player_cache"]
    match_stats = stats["match_cache"]
    stats_stats = stats["stats_cache"]
    
    # Calculate total entries (if keyspace info available)
    total_entries = 0
    for cache_stats in stats.values():
        if cache_stats.get("connected") and cache_stats.get("keyspace"):
            for db_info in cache_stats["keyspace"].values():
                if "keys" in db_info:
                    total_entries += db_info["keys"]
    
    return {
        "player_cache": player_stats,
        "match_cache": match_stats,  
        "stats_cache": stats_stats,
        "total_entries": total_entries,
        "redis_enabled": True
    }


async def clear_all_caches() -> None:
    """Clear all Redis caches."""
    results = await redis_clear_all_caches()
    logger.info(f"Redis caches cleared: {results}")