"""
Redis-based caching system for FACEIT Bot
Replaces in-memory cache with distributed Redis cache
"""
import asyncio
import json
import logging
from typing import Any, Dict, Optional, Union, List
from datetime import datetime, timedelta
import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import RedisError, ConnectionError

logger = logging.getLogger(__name__)


class RedisCache:
    """Async Redis cache with TTL support and error handling"""
    
    def __init__(self, 
                 redis_url: str = "redis://localhost:6379",
                 default_ttl: int = 300,
                 max_retries: int = 3):
        self.redis_url = redis_url
        self.default_ttl = default_ttl
        self.max_retries = max_retries
        self.redis: Optional[Redis] = None
        self._connected = False
        
    async def connect(self):
        """Connect to Redis with retry logic"""
        for attempt in range(self.max_retries):
            try:
                self.redis = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30
                )
                
                # Test connection
                await self.redis.ping()
                self._connected = True
                logger.info(f"✅ Connected to Redis at {self.redis_url}")
                return
                
            except (ConnectionError, RedisError) as e:
                logger.warning(f"Redis connection attempt {attempt + 1}/{self.max_retries} failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"❌ Failed to connect to Redis after {self.max_retries} attempts")
                    self._connected = False
                    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()
            self._connected = False
            logger.info("Redis connection closed")
            
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        return self._connected
        
    def _serialize_value(self, value: Any) -> str:
        """Serialize value to JSON string"""
        if isinstance(value, (dict, list)):
            return json.dumps(value, default=str, ensure_ascii=False)
        elif isinstance(value, datetime):
            return value.isoformat()
        else:
            return str(value)
            
    def _deserialize_value(self, value: str) -> Any:
        """Deserialize JSON string to value"""
        if not value:
            return None
            
        try:
            # Try to parse as JSON
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # If not JSON, return as string
            return value
            
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.is_connected():
            logger.warning("Redis not connected, cache miss")
            return None
            
        try:
            value = await self.redis.get(key)
            if value is None:
                return None
                
            result = self._deserialize_value(value)
            logger.debug(f"Cache HIT: {key}")
            return result
            
        except RedisError as e:
            logger.error(f"Redis GET error for key '{key}': {e}")
            return None
            
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with TTL"""
        if not self.is_connected():
            logger.warning("Redis not connected, cache write skipped")
            return False
            
        try:
            ttl = ttl or self.default_ttl
            serialized_value = self._serialize_value(value)
            
            await self.redis.setex(key, ttl, serialized_value)
            logger.debug(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
            
        except RedisError as e:
            logger.error(f"Redis SET error for key '{key}': {e}")
            return False
            
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.is_connected():
            return False
            
        try:
            result = await self.redis.delete(key)
            logger.debug(f"Cache DELETE: {key}")
            return bool(result)
            
        except RedisError as e:
            logger.error(f"Redis DELETE error for key '{key}': {e}")
            return False
            
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.is_connected():
            return False
            
        try:
            result = await self.redis.exists(key)
            return bool(result)
        except RedisError as e:
            logger.error(f"Redis EXISTS error for key '{key}': {e}")
            return False
            
    async def clear(self) -> bool:
        """Clear all cache (use with caution!)"""
        if not self.is_connected():
            return False
            
        try:
            await self.redis.flushdb()
            logger.info("Cache cleared")
            return True
        except RedisError as e:
            logger.error(f"Redis CLEAR error: {e}")
            return False
            
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.is_connected():
            return {"connected": False}
            
        try:
            info = await self.redis.info("keyspace")
            memory_info = await self.redis.info("memory")
            
            stats = {
                "connected": True,
                "keyspace": info,
                "memory_used": memory_info.get("used_memory_human", "N/A"),
                "memory_peak": memory_info.get("used_memory_peak_human", "N/A"),
                "hits": await self.redis.info("stats").get("keyspace_hits", 0),
                "misses": await self.redis.info("stats").get("keyspace_misses", 0),
            }
            
            # Calculate hit rate
            hits = stats["hits"] 
            misses = stats["misses"]
            total = hits + misses
            stats["hit_rate"] = round((hits / total * 100) if total > 0 else 0, 2)
            
            return stats
            
        except RedisError as e:
            logger.error(f"Redis STATS error: {e}")
            return {"connected": False, "error": str(e)}
            
    async def get_keys_pattern(self, pattern: str) -> List[str]:
        """Get keys matching pattern"""
        if not self.is_connected():
            return []
            
        try:
            keys = await self.redis.keys(pattern)
            return keys
        except RedisError as e:
            logger.error(f"Redis KEYS error for pattern '{pattern}': {e}")
            return []


class CacheDecorator:
    """Decorator for caching function results"""
    
    def __init__(self, cache: RedisCache, ttl: Optional[int] = None, key_prefix: str = ""):
        self.cache = cache
        self.ttl = ttl
        self.key_prefix = key_prefix
        
    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key_parts = [self.key_prefix, func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(filter(None, key_parts))
            
            # Try to get from cache
            cached_result = await self.cache.get(cache_key)
            if cached_result is not None:
                return cached_result
                
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await self.cache.set(cache_key, result, self.ttl)
            return result
            
        return wrapper


# Global cache instances
player_cache = RedisCache(default_ttl=300)  # 5 minutes
match_cache = RedisCache(default_ttl=120)   # 2 minutes  
stats_cache = RedisCache(default_ttl=600)   # 10 minutes


async def init_redis_cache(redis_url: str = "redis://localhost:6379"):
    """Initialize all Redis cache instances"""
    logger.info("Initializing Redis cache...")
    
    # Update URLs for all cache instances
    player_cache.redis_url = redis_url
    match_cache.redis_url = redis_url
    stats_cache.redis_url = redis_url
    
    # Connect all instances
    await asyncio.gather(
        player_cache.connect(),
        match_cache.connect(),
        stats_cache.connect(),
        return_exceptions=True
    )
    
    # Check connections
    connected = [
        player_cache.is_connected(),
        match_cache.is_connected(),
        stats_cache.is_connected()
    ]
    
    if all(connected):
        logger.info("✅ All Redis cache instances connected")
    elif any(connected):
        logger.warning("⚠️ Some Redis cache instances failed to connect")
    else:
        logger.error("❌ All Redis cache instances failed to connect")


async def close_redis_cache():
    """Close all Redis cache connections"""
    await asyncio.gather(
        player_cache.disconnect(),
        match_cache.disconnect(), 
        stats_cache.disconnect(),
        return_exceptions=True
    )
    logger.info("Redis cache connections closed")


async def get_all_cache_stats() -> Dict[str, Any]:
    """Get statistics from all cache instances"""
    return {
        "player_cache": await player_cache.get_stats(),
        "match_cache": await match_cache.get_stats(),
        "stats_cache": await stats_cache.get_stats(),
    }


async def clear_all_caches() -> Dict[str, bool]:
    """Clear all cache instances"""
    results = await asyncio.gather(
        player_cache.clear(),
        match_cache.clear(),
        stats_cache.clear(),
        return_exceptions=True
    )
    
    return {
        "player_cache": results[0] if not isinstance(results[0], Exception) else False,
        "match_cache": results[1] if not isinstance(results[1], Exception) else False,
        "stats_cache": results[2] if not isinstance(results[2], Exception) else False,
    }


# Decorators for common use cases
def cache_player_data(ttl: int = 300):
    """Decorator for caching player data"""
    return CacheDecorator(player_cache, ttl=ttl, key_prefix="player")


def cache_match_data(ttl: int = 120):
    """Decorator for caching match data"""
    return CacheDecorator(match_cache, ttl=ttl, key_prefix="match")


def cache_stats_data(ttl: int = 600):
    """Decorator for caching stats data"""
    return CacheDecorator(stats_cache, ttl=ttl, key_prefix="stats")