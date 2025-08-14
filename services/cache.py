"""
Cache Service implementation with unified cache management.

Provides comprehensive cache orchestration and management:
- Redis cache operations and coordination
- Multi-level caching strategy implementation  
- Cache invalidation and cleanup management
- Cache warming and preloading strategies
- Performance monitoring and optimization
- Cache statistics and analytics
- Integration with all other services
"""

import logging
from typing import Optional, Dict, Any, List, Union, Callable
from datetime import datetime, timedelta
import asyncio
import json
import hashlib
import time
import uuid

from utils.redis_cache import (
    RedisCache, player_cache, match_cache, stats_cache, 
    cache_player_data, cache_stats_data
)
from .base import BaseService, ServiceResult, ServiceError, EventType, ServiceEvent

logger = logging.getLogger(__name__)


class CacheService(BaseService):
    """
    Service for unified cache management and orchestration.
    
    Handles:
    - Multi-level cache coordination
    - Cache invalidation strategies
    - Performance monitoring and optimization
    - Cache warming and preloading
    - Statistics and analytics
    - Integration with all services
    - Background maintenance tasks
    """
    
    # Cache configuration
    CACHE_CONFIGS = {
        "player": {
            "ttl": 300,  # 5 minutes
            "max_size": 1000,
            "warm_on_startup": True
        },
        "match": {
            "ttl": 180,  # 3 minutes
            "max_size": 500,
            "warm_on_startup": False
        },
        "stats": {
            "ttl": 600,  # 10 minutes
            "max_size": 2000,
            "warm_on_startup": False
        },
        "analysis": {
            "ttl": 900,  # 15 minutes
            "max_size": 100,
            "warm_on_startup": False
        },
        "subscription": {
            "ttl": 1800,  # 30 minutes
            "max_size": 500,
            "warm_on_startup": False
        }
    }
    
    def __init__(self, redis_caches: Optional[Dict[str, RedisCache]] = None):
        """
        Initialize cache service with Redis cache instances.
        
        Args:
            redis_caches: Dictionary of named Redis cache instances
        """
        super().__init__()
        
        # Initialize cache instances
        self.caches = redis_caches or {
            "player": player_cache,
            "match": match_cache,
            "stats": stats_cache
        }
        
        # Cache statistics
        self._cache_stats = {
            cache_name: {
                "hits": 0,
                "misses": 0,
                "sets": 0,
                "deletes": 0,
                "errors": 0
            }
            for cache_name in self.caches.keys()
        }
        
        # Background task references
        self._maintenance_task = None
        self._stats_task = None
        
        # Setup event handlers
        self._setup_event_handlers()
    
    def _setup_event_handlers(self):
        """Setup event handlers for cache invalidation."""
        logger.info("Cache service event handlers initialized")
    
    # Core cache operations
    async def get(
        self,
        cache_name: str,
        key: str,
        default: Any = None
    ) -> ServiceResult[Any]:
        """
        Get value from specified cache.
        
        Args:
            cache_name: Name of cache instance
            key: Cache key
            default: Default value if key not found
            
        Returns:
            ServiceResult with cached value or error
        """
        try:
            cache = self._get_cache_instance(cache_name)
            if not cache:
                return ServiceResult.error_result(
                    ServiceError(f"Cache '{cache_name}' not found", "CACHE_NOT_FOUND")
                )
            
            # Attempt to get value
            start_time = time.time()
            value = await cache.get(key)
            operation_time = (time.time() - start_time) * 1000
            
            if value is not None:
                self._record_cache_hit(cache_name, operation_time)
                return ServiceResult.success_result(value)
            else:
                self._record_cache_miss(cache_name, operation_time)
                return ServiceResult.success_result(default)
        
        except Exception as e:
            self._record_cache_error(cache_name)
            logger.error(f"Cache get error for {cache_name}:{key}: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Cache get failed: {e}", "CACHE_GET_ERROR")
            )
    
    async def set(
        self,
        cache_name: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> ServiceResult[bool]:
        """
        Set value in specified cache.
        
        Args:
            cache_name: Name of cache instance
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (optional)
            
        Returns:
            ServiceResult with success status
        """
        try:
            cache = self._get_cache_instance(cache_name)
            if not cache:
                return ServiceResult.error_result(
                    ServiceError(f"Cache '{cache_name}' not found", "CACHE_NOT_FOUND")
                )
            
            # Use default TTL if not provided
            if ttl is None:
                ttl = self.CACHE_CONFIGS.get(cache_name, {}).get("ttl", 300)
            
            # Set value
            start_time = time.time()
            await cache.set(key, value, ttl)
            operation_time = (time.time() - start_time) * 1000
            
            self._record_cache_set(cache_name, operation_time)
            return ServiceResult.success_result(True)
        
        except Exception as e:
            self._record_cache_error(cache_name)
            logger.error(f"Cache set error for {cache_name}:{key}: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Cache set failed: {e}", "CACHE_SET_ERROR")
            )
    
    async def delete(
        self,
        cache_name: str,
        key: str
    ) -> ServiceResult[bool]:
        """
        Delete key from specified cache.
        
        Args:
            cache_name: Name of cache instance
            key: Cache key to delete
            
        Returns:
            ServiceResult with success status
        """
        try:
            cache = self._get_cache_instance(cache_name)
            if not cache:
                return ServiceResult.error_result(
                    ServiceError(f"Cache '{cache_name}' not found", "CACHE_NOT_FOUND")
                )
            
            start_time = time.time()
            await cache.delete(key)
            operation_time = (time.time() - start_time) * 1000
            
            self._record_cache_delete(cache_name, operation_time)
            return ServiceResult.success_result(True)
        
        except Exception as e:
            self._record_cache_error(cache_name)
            logger.error(f"Cache delete error for {cache_name}:{key}: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Cache delete failed: {e}", "CACHE_DELETE_ERROR")
            )
    
    async def invalidate_pattern(
        self,
        cache_name: str,
        pattern: str
    ) -> ServiceResult[int]:
        """
        Invalidate all keys matching pattern in specified cache.
        
        Args:
            cache_name: Name of cache instance
            pattern: Key pattern to match (supports wildcards)
            
        Returns:
            ServiceResult with number of invalidated keys
        """
        try:
            cache = self._get_cache_instance(cache_name)
            if not cache:
                return ServiceResult.error_result(
                    ServiceError(f"Cache '{cache_name}' not found", "CACHE_NOT_FOUND")
                )
            
            # Get matching keys
            keys = await cache.get_keys_pattern(pattern)
            
            # Delete all matching keys
            deleted_count = 0
            for key in keys:
                try:
                    await cache.delete(key)
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete cache key {key}: {e}")
            
            logger.info(f"Invalidated {deleted_count} keys matching pattern '{pattern}' in {cache_name}")
            return ServiceResult.success_result(deleted_count)
        
        except Exception as e:
            self._record_cache_error(cache_name)
            logger.error(f"Cache pattern invalidation error for {cache_name}:{pattern}: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Cache invalidation failed: {e}", "CACHE_INVALIDATION_ERROR")
            )
    
    # Multi-cache operations
    async def get_from_multiple(
        self,
        cache_configs: List[Dict[str, Any]],
        default: Any = None
    ) -> ServiceResult[Any]:
        """
        Get value from multiple caches in priority order.
        
        Args:
            cache_configs: List of cache configs with 'cache_name' and 'key'
            default: Default value if not found in any cache
            
        Returns:
            ServiceResult with first found value
        """
        try:
            for config in cache_configs:
                cache_name = config.get("cache_name")
                key = config.get("key")
                
                if not cache_name or not key:
                    continue
                
                result = await self.get(cache_name, key)
                if result.success and result.data is not None:
                    return result
            
            return ServiceResult.success_result(default)
        
        except Exception as e:
            logger.error(f"Multi-cache get error: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Multi-cache get failed: {e}", "MULTI_CACHE_ERROR")
            )
    
    async def set_in_multiple(
        self,
        cache_configs: List[Dict[str, Any]],
        value: Any
    ) -> ServiceResult[Dict[str, bool]]:
        """
        Set value in multiple caches.
        
        Args:
            cache_configs: List of cache configs with 'cache_name', 'key', and optional 'ttl'
            value: Value to cache
            
        Returns:
            ServiceResult with success status for each cache
        """
        try:
            results = {}
            
            for config in cache_configs:
                cache_name = config.get("cache_name")
                key = config.get("key")
                ttl = config.get("ttl")
                
                if not cache_name or not key:
                    results[f"{cache_name}:{key}"] = False
                    continue
                
                result = await self.set(cache_name, key, value, ttl)
                results[f"{cache_name}:{key}"] = result.success
            
            return ServiceResult.success_result(results)
        
        except Exception as e:
            logger.error(f"Multi-cache set error: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Multi-cache set failed: {e}", "MULTI_CACHE_ERROR")
            )
    
    # Cache warming and preloading
    async def warm_cache(
        self,
        cache_name: str,
        warm_function: Callable,
        warm_keys: List[str]
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Warm up cache with preloaded data.
        
        Args:
            cache_name: Name of cache to warm
            warm_function: Function to generate cache data
            warm_keys: List of keys to warm
            
        Returns:
            ServiceResult with warming statistics
        """
        try:
            start_time = time.time()
            successful_warms = 0
            failed_warms = 0
            
            logger.info(f"Starting cache warming for {cache_name} with {len(warm_keys)} keys")
            
            # Process keys in batches to avoid overwhelming the system
            batch_size = 10
            for i in range(0, len(warm_keys), batch_size):
                batch_keys = warm_keys[i:i + batch_size]
                
                # Process batch in parallel
                tasks = []
                for key in batch_keys:
                    task = self._warm_single_key(cache_name, key, warm_function)
                    tasks.append(task)
                
                # Wait for batch completion
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        failed_warms += 1
                    else:
                        successful_warms += 1
                
                # Small delay between batches
                await asyncio.sleep(0.1)
            
            total_time = time.time() - start_time
            
            warm_stats = {
                "cache_name": cache_name,
                "total_keys": len(warm_keys),
                "successful_warms": successful_warms,
                "failed_warms": failed_warms,
                "success_rate": round((successful_warms / len(warm_keys) * 100), 2),
                "total_time_seconds": round(total_time, 2)
            }
            
            logger.info(f"Cache warming completed: {warm_stats}")
            return ServiceResult.success_result(warm_stats)
        
        except Exception as e:
            logger.error(f"Cache warming failed for {cache_name}: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Cache warming failed: {e}", "CACHE_WARMING_ERROR")
            )
    
    async def _warm_single_key(
        self,
        cache_name: str,
        key: str,
        warm_function: Callable
    ) -> bool:
        """Warm a single cache key."""
        try:
            # Check if key already exists
            result = await self.get(cache_name, key)
            if result.success and result.data is not None:
                return True  # Already cached
            
            # Generate data using warm function
            if asyncio.iscoroutinefunction(warm_function):
                data = await warm_function(key)
            else:
                data = warm_function(key)
            
            if data is not None:
                # Cache the data
                set_result = await self.set(cache_name, key, data)
                return set_result.success
            
            return False
        
        except Exception as e:
            logger.warning(f"Failed to warm cache key {key}: {e}")
            return False
    
    # Cache statistics and monitoring
    async def get_cache_statistics(
        self,
        cache_name: Optional[str] = None
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Get comprehensive cache statistics.
        
        Args:
            cache_name: Optional specific cache name, if None returns all caches
            
        Returns:
            ServiceResult with cache statistics
        """
        try:
            if cache_name:
                if cache_name not in self.caches:
                    return ServiceResult.error_result(
                        ServiceError(f"Cache '{cache_name}' not found", "CACHE_NOT_FOUND")
                    )
                
                stats = await self._get_single_cache_stats(cache_name)
                return ServiceResult.success_result(stats)
            else:
                # Get stats for all caches
                all_stats = {}
                for cache_name in self.caches.keys():
                    try:
                        all_stats[cache_name] = await self._get_single_cache_stats(cache_name)
                    except Exception as e:
                        all_stats[cache_name] = {"error": str(e)}
                
                # Add aggregate statistics
                aggregate_stats = self._calculate_aggregate_stats(all_stats)
                
                return ServiceResult.success_result({
                    "individual_caches": all_stats,
                    "aggregate": aggregate_stats,
                    "timestamp": datetime.now().isoformat()
                })
        
        except Exception as e:
            logger.error(f"Error getting cache statistics: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to get cache statistics: {e}", "CACHE_STATS_ERROR")
            )
    
    async def _get_single_cache_stats(self, cache_name: str) -> Dict[str, Any]:
        """Get statistics for a single cache."""
        cache = self.caches[cache_name]
        operation_stats = self._cache_stats[cache_name]
        
        # Calculate hit rate
        total_operations = operation_stats["hits"] + operation_stats["misses"]
        hit_rate = round(
            (operation_stats["hits"] / total_operations * 100) if total_operations > 0 else 0,
            2
        )
        
        stats = {
            "cache_name": cache_name,
            "connection_status": "connected" if await self._test_cache_connection(cache) else "disconnected",
            "operations": operation_stats.copy(),
            "hit_rate_percentage": hit_rate,
            "configuration": self.CACHE_CONFIGS.get(cache_name, {}),
        }
        
        # Get Redis-specific stats if available
        try:
            if hasattr(cache, 'info'):
                redis_info = await cache.info()
                stats["redis_info"] = {
                    "used_memory": redis_info.get("used_memory_human", "unknown"),
                    "connected_clients": redis_info.get("connected_clients", "unknown"),
                    "total_commands_processed": redis_info.get("total_commands_processed", "unknown"),
                    "keyspace_hits": redis_info.get("keyspace_hits", "unknown"),
                    "keyspace_misses": redis_info.get("keyspace_misses", "unknown")
                }
        except Exception as e:
            logger.debug(f"Could not get Redis info for {cache_name}: {e}")
        
        return stats
    
    def _calculate_aggregate_stats(self, all_stats: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate aggregate statistics across all caches."""
        total_hits = 0
        total_misses = 0
        total_sets = 0
        total_deletes = 0
        total_errors = 0
        connected_caches = 0
        
        for cache_name, stats in all_stats.items():
            if "error" in stats:
                continue
            
            operations = stats.get("operations", {})
            total_hits += operations.get("hits", 0)
            total_misses += operations.get("misses", 0)
            total_sets += operations.get("sets", 0)
            total_deletes += operations.get("deletes", 0)
            total_errors += operations.get("errors", 0)
            
            if stats.get("connection_status") == "connected":
                connected_caches += 1
        
        total_operations = total_hits + total_misses
        overall_hit_rate = round(
            (total_hits / total_operations * 100) if total_operations > 0 else 0,
            2
        )
        
        return {
            "total_caches": len(all_stats),
            "connected_caches": connected_caches,
            "overall_hit_rate_percentage": overall_hit_rate,
            "total_operations": {
                "hits": total_hits,
                "misses": total_misses,
                "sets": total_sets,
                "deletes": total_deletes,
                "errors": total_errors
            }
        }
    
    # Cache maintenance and cleanup
    async def cleanup_expired_keys(
        self,
        cache_name: Optional[str] = None
    ) -> ServiceResult[Dict[str, int]]:
        """
        Clean up expired keys from caches.
        
        Args:
            cache_name: Optional specific cache name, if None cleans all caches
            
        Returns:
            ServiceResult with cleanup statistics
        """
        try:
            cleanup_stats = {}
            
            caches_to_clean = [cache_name] if cache_name else list(self.caches.keys())
            
            for cache_name in caches_to_clean:
                cache = self._get_cache_instance(cache_name)
                if not cache:
                    cleanup_stats[cache_name] = {"error": "Cache not found"}
                    continue
                
                try:
                    # This would typically involve scanning for expired keys
                    # For Redis, expired keys are usually cleaned up automatically
                    # But we can force cleanup of specific patterns if needed
                    
                    cleaned_count = 0  # Placeholder for actual cleanup logic
                    cleanup_stats[cache_name] = {"cleaned_keys": cleaned_count}
                    
                except Exception as e:
                    cleanup_stats[cache_name] = {"error": str(e)}
            
            return ServiceResult.success_result(cleanup_stats)
        
        except Exception as e:
            logger.error(f"Error during cache cleanup: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Cache cleanup failed: {e}", "CACHE_CLEANUP_ERROR")
            )
    
    async def clear_all_caches(
        self,
        confirm: bool = False
    ) -> ServiceResult[Dict[str, bool]]:
        """
        Clear all data from all caches.
        
        Args:
            confirm: Confirmation flag for safety
            
        Returns:
            ServiceResult with clear status for each cache
        """
        if not confirm:
            return ServiceResult.error_result(
                ServiceError("Cache clearing must be confirmed", "CONFIRMATION_REQUIRED")
            )
        
        try:
            clear_results = {}
            
            for cache_name, cache in self.caches.items():
                try:
                    if hasattr(cache, 'flushdb'):
                        await cache.flushdb()
                    elif hasattr(cache, 'clear'):
                        await cache.clear()
                    else:
                        # Fallback: delete all keys by pattern
                        keys = await cache.get_keys_pattern("*")
                        for key in keys:
                            await cache.delete(key)
                    
                    clear_results[cache_name] = True
                    logger.warning(f"Cleared all data from cache: {cache_name}")
                    
                except Exception as e:
                    clear_results[cache_name] = False
                    logger.error(f"Failed to clear cache {cache_name}: {e}")
            
            # Reset statistics
            for cache_name in self._cache_stats:
                self._cache_stats[cache_name] = {
                    "hits": 0,
                    "misses": 0,
                    "sets": 0,
                    "deletes": 0,
                    "errors": 0
                }
            
            return ServiceResult.success_result(clear_results)
        
        except Exception as e:
            logger.error(f"Error clearing caches: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Cache clearing failed: {e}", "CACHE_CLEAR_ERROR")
            )
    
    # Event handling for cache invalidation
    async def handle_event(self, event: ServiceEvent):
        """Handle service events for cache invalidation."""
        try:
            if event.event_type == EventType.USER_UPDATED:
                await self._invalidate_user_caches(event.entity_id)
            elif event.event_type == EventType.SUBSCRIPTION_UPGRADED:
                await self._invalidate_subscription_caches(event.entity_id)
            elif event.event_type == EventType.MATCH_ANALYZED:
                await self._invalidate_match_caches(event.data.get("match_id"))
            elif event.event_type == EventType.CACHE_CLEARED:
                await self._handle_cache_clear_event(event)
        
        except Exception as e:
            logger.warning(f"Failed to handle cache invalidation event {event.event_type}: {e}")
    
    async def _invalidate_user_caches(self, user_id: Union[str, uuid.UUID, int]):
        """Invalidate user-related caches."""
        patterns = [
            f"users:*{user_id}*",
            f"profile:{user_id}*",
            f"subscription:*{user_id}*"
        ]
        
        for pattern in patterns:
            for cache_name in self.caches.keys():
                await self.invalidate_pattern(cache_name, pattern)
    
    async def _invalidate_subscription_caches(self, user_id: Union[str, uuid.UUID, int]):
        """Invalidate subscription-related caches."""
        patterns = [
            f"subscription:*{user_id}*",
            f"limits:*{user_id}*"
        ]
        
        for pattern in patterns:
            await self.invalidate_pattern("stats", pattern)
    
    async def _invalidate_match_caches(self, match_id: Optional[str]):
        """Invalidate match-related caches."""
        if not match_id:
            return
        
        patterns = [
            f"match:*{match_id}*",
            f"analysis:*{match_id}*"
        ]
        
        for pattern in patterns:
            await self.invalidate_pattern("match", pattern)
    
    async def _handle_cache_clear_event(self, event: ServiceEvent):
        """Handle cache clear events."""
        cache_name = event.data.get("cache_name")
        if cache_name and cache_name in self.caches:
            logger.info(f"Handling cache clear event for {cache_name}")
            # Additional processing if needed
    
    # Background maintenance tasks
    async def start_maintenance_tasks(self):
        """Start background maintenance tasks."""
        try:
            # Start periodic cleanup task
            self._maintenance_task = asyncio.create_task(self._maintenance_loop())
            
            # Start statistics collection task
            self._stats_task = asyncio.create_task(self._stats_collection_loop())
            
            logger.info("Cache maintenance tasks started")
        
        except Exception as e:
            logger.error(f"Failed to start maintenance tasks: {e}")
    
    async def stop_maintenance_tasks(self):
        """Stop background maintenance tasks."""
        try:
            if self._maintenance_task:
                self._maintenance_task.cancel()
            
            if self._stats_task:
                self._stats_task.cancel()
            
            logger.info("Cache maintenance tasks stopped")
        
        except Exception as e:
            logger.error(f"Error stopping maintenance tasks: {e}")
    
    async def _maintenance_loop(self):
        """Background maintenance loop."""
        while True:
            try:
                # Perform maintenance every 30 minutes
                await asyncio.sleep(1800)
                
                # Cleanup expired keys
                await self.cleanup_expired_keys()
                
                logger.debug("Cache maintenance completed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache maintenance loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _stats_collection_loop(self):
        """Background statistics collection loop."""
        while True:
            try:
                # Collect stats every 10 minutes
                await asyncio.sleep(600)
                
                # Log cache statistics
                stats_result = await self.get_cache_statistics()
                if stats_result.success:
                    stats = stats_result.data
                    logger.info(f"Cache statistics: {stats.get('aggregate', {})}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in stats collection loop: {e}")
                await asyncio.sleep(60)
    
    # Helper methods
    def _get_cache_instance(self, cache_name: str) -> Optional[RedisCache]:
        """Get cache instance by name."""
        return self.caches.get(cache_name)
    
    async def _test_cache_connection(self, cache: RedisCache) -> bool:
        """Test cache connection."""
        try:
            await cache.ping()
            return True
        except Exception:
            return False
    
    def _record_cache_hit(self, cache_name: str, operation_time: float):
        """Record cache hit statistics."""
        if cache_name in self._cache_stats:
            self._cache_stats[cache_name]["hits"] += 1
    
    def _record_cache_miss(self, cache_name: str, operation_time: float):
        """Record cache miss statistics."""
        if cache_name in self._cache_stats:
            self._cache_stats[cache_name]["misses"] += 1
    
    def _record_cache_set(self, cache_name: str, operation_time: float):
        """Record cache set statistics."""
        if cache_name in self._cache_stats:
            self._cache_stats[cache_name]["sets"] += 1
    
    def _record_cache_delete(self, cache_name: str, operation_time: float):
        """Record cache delete statistics."""
        if cache_name in self._cache_stats:
            self._cache_stats[cache_name]["deletes"] += 1
    
    def _record_cache_error(self, cache_name: str):
        """Record cache error statistics."""
        if cache_name in self._cache_stats:
            self._cache_stats[cache_name]["errors"] += 1
    
    # Health check implementation
    async def health_check(self) -> ServiceResult[Dict[str, Any]]:
        """Perform cache service health check."""
        try:
            health_data = await self._base_health_check()
            
            # Test all cache connections
            cache_health = {}
            overall_healthy = True
            
            for cache_name, cache in self.caches.items():
                try:
                    connection_healthy = await self._test_cache_connection(cache)
                    cache_health[cache_name] = {
                        "status": "connected" if connection_healthy else "disconnected",
                        "operations": self._cache_stats.get(cache_name, {})
                    }
                    
                    if not connection_healthy:
                        overall_healthy = False
                        
                except Exception as e:
                    cache_health[cache_name] = {
                        "status": f"error: {e}",
                        "operations": self._cache_stats.get(cache_name, {})
                    }
                    overall_healthy = False
            
            health_data["cache_instances"] = cache_health
            health_data["overall_cache_health"] = "healthy" if overall_healthy else "degraded"
            
            if not overall_healthy:
                health_data["status"] = "degraded"
            
            return ServiceResult.success_result(health_data)
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Health check failed: {e}", "HEALTH_CHECK_ERROR")
            )
    
    def __del__(self):
        """Cleanup on destruction."""
        try:
            if self._maintenance_task and not self._maintenance_task.cancelled():
                self._maintenance_task.cancel()
            
            if self._stats_task and not self._stats_task.cancelled():
                self._stats_task.cancel()
        except Exception:
            pass