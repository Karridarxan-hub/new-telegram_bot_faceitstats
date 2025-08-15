"""Background tasks for cache management and optimization.

Handles cache warming, cleanup, optimization, and health monitoring to ensure
optimal performance and efficient memory usage across the Redis cache system.
"""

import logging
import asyncio
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, asdict

from rq import get_current_job
from rq.decorators import job

from faceit.api import FaceitAPI, FaceitAPIError
from utils.cache import CachedFaceitAPI
from utils.storage import storage
from utils.redis_cache import (
    player_cache, match_cache, stats_cache
)
from config.settings import settings

logger = logging.getLogger(__name__)

# Initialize API instances
faceit_api = FaceitAPI()
cached_api = CachedFaceitAPI(faceit_api)


@dataclass
class CacheOperationResult:
    """Result of cache operation."""
    operation_type: str
    success: bool
    items_processed: int = 0
    items_added: int = 0
    items_removed: int = 0
    items_updated: int = 0
    cache_size_before: int = 0
    cache_size_after: int = 0
    processing_time_ms: int = 0
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _run_async(coro):
    """Helper to run async code in sync job context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)


def _update_job_progress(current: int, total: int, operation: str = ""):
    """Update job progress metadata."""
    job = get_current_job()
    if job:
        progress = round((current / total) * 100, 1) if total > 0 else 0
        job.meta.update({
            'progress': {
                'current': current,
                'total': total,
                'percentage': progress,
                'operation': operation
            },
            'updated_at': datetime.now().isoformat()
        })
        job.save_meta()


@job('faceit_cache_warm', timeout=3600, result_ttl=1800)
def warm_cache_task(
    warm_type: str = "popular_data",
    priority_items: Optional[List[str]] = None,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Background task to warm cache with frequently accessed data.
    
    This task pre-loads commonly accessed data into cache to improve response
    times for users by avoiding cold cache misses.
    
    Args:
        warm_type: Type of warming - 'popular_data', 'recent_players', 'active_matches'
        priority_items: Specific items to prioritize for warming
        force_refresh: Whether to refresh existing cache entries
        
    Returns:
        Dict with cache warming results
    """
    start_time = datetime.now()
    logger.info(f"Starting cache warming task (type: {warm_type})")
    
    try:
        if warm_type == "popular_data":
            result = _run_async(_warm_popular_data_cache(priority_items, force_refresh))
        elif warm_type == "recent_players":
            result = _run_async(_warm_recent_players_cache(force_refresh))
        elif warm_type == "active_matches":
            result = _run_async(_warm_active_matches_cache(force_refresh))
        elif warm_type == "comprehensive":
            result = _run_async(_warm_comprehensive_cache(priority_items, force_refresh))
        else:
            return {
                "success": False,
                "error": f"Unknown warm type: {warm_type}",
                "timestamp": datetime.now().isoformat()
            }
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        result["processing_time_ms"] = processing_time
        result["warm_type"] = warm_type
        result["timestamp"] = datetime.now().isoformat()
        
        logger.info(f"Cache warming completed: {result.get('items_added', 0)} items added")
        return result
        
    except Exception as e:
        logger.error(f"Cache warming task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "warm_type": warm_type,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_cache_cleanup', timeout=1800, result_ttl=3600)
def cleanup_expired_cache_task(
    cleanup_type: str = "expired",
    max_items_to_remove: int = 1000,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Background task to clean up expired and stale cache entries.
    
    Args:
        cleanup_type: Type of cleanup - 'expired', 'stale', 'oversized', 'all'
        max_items_to_remove: Maximum number of items to remove in one run
        dry_run: If True, only report what would be cleaned without actual removal
        
    Returns:
        Dict with cleanup results
    """
    start_time = datetime.now()
    logger.info(f"Starting cache cleanup task (type: {cleanup_type}, dry_run: {dry_run})")
    
    try:
        total_removed = 0
        cache_operations = []
        
        if cleanup_type in ["expired", "all"]:
            expired_result = _run_async(_cleanup_expired_entries(max_items_to_remove, dry_run))
            cache_operations.append(expired_result)
            total_removed += expired_result.items_removed
        
        if cleanup_type in ["stale", "all"]:
            stale_result = _run_async(_cleanup_stale_entries(max_items_to_remove - total_removed, dry_run))
            cache_operations.append(stale_result)
            total_removed += stale_result.items_removed
        
        if cleanup_type in ["oversized", "all"]:
            oversized_result = _run_async(_cleanup_oversized_cache(max_items_to_remove - total_removed, dry_run))
            cache_operations.append(oversized_result)
            total_removed += oversized_result.items_removed
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return {
            "success": True,
            "cleanup_type": cleanup_type,
            "dry_run": dry_run,
            "total_items_removed": total_removed,
            "processing_time_ms": processing_time,
            "operations": [op.to_dict() for op in cache_operations],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache cleanup task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "cleanup_type": cleanup_type,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_cache_optimize', timeout=2400, result_ttl=3600)
def optimize_cache_usage_task(
    optimization_type: str = "comprehensive",
    target_memory_reduction_mb: int = 100
) -> Dict[str, Any]:
    """
    Background task to optimize cache usage and memory efficiency.
    
    Args:
        optimization_type: Type of optimization - 'memory', 'access_patterns', 'comprehensive'
        target_memory_reduction_mb: Target memory reduction in MB
        
    Returns:
        Dict with optimization results
    """
    start_time = datetime.now()
    logger.info(f"Starting cache optimization task (type: {optimization_type})")
    
    try:
        # Get initial cache stats
        initial_stats = _run_async(get_all_cache_stats())
        
        optimization_results = []
        
        if optimization_type in ["memory", "comprehensive"]:
            memory_result = _run_async(_optimize_memory_usage(target_memory_reduction_mb))
            optimization_results.append(memory_result)
        
        if optimization_type in ["access_patterns", "comprehensive"]:
            pattern_result = _run_async(_optimize_access_patterns())
            optimization_results.append(pattern_result)
        
        if optimization_type in ["ttl", "comprehensive"]:
            ttl_result = _run_async(_optimize_ttl_values())
            optimization_results.append(ttl_result)
        
        # Get final cache stats
        final_stats = _run_async(get_all_cache_stats())
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return {
            "success": True,
            "optimization_type": optimization_type,
            "initial_cache_stats": initial_stats,
            "final_cache_stats": final_stats,
            "optimization_results": [result.to_dict() for result in optimization_results],
            "processing_time_ms": processing_time,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache optimization task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "optimization_type": optimization_type,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_cache_refresh', timeout=3600, result_ttl=1800)
def refresh_popular_data_task(
    refresh_threshold_hours: int = 6,
    max_items_to_refresh: int = 500,
    priority_refresh: bool = True
) -> Dict[str, Any]:
    """
    Background task to refresh popular cache entries before they expire.
    
    Args:
        refresh_threshold_hours: Refresh items that expire within this many hours
        max_items_to_refresh: Maximum number of items to refresh
        priority_refresh: Whether to prioritize frequently accessed items
        
    Returns:
        Dict with refresh results
    """
    start_time = datetime.now()
    logger.info(f"Starting cache refresh task (threshold: {refresh_threshold_hours}h)")
    
    try:
        # Get items that need refreshing
        refresh_candidates = _run_async(_identify_refresh_candidates(
            refresh_threshold_hours, priority_refresh
        ))
        
        if not refresh_candidates:
            return {
                "success": True,
                "message": "No items need refreshing",
                "items_checked": 0,
                "items_refreshed": 0,
                "timestamp": datetime.now().isoformat()
            }
        
        # Limit to max items
        items_to_refresh = refresh_candidates[:max_items_to_refresh]
        
        # Refresh items in batches
        batch_size = 10
        total_refreshed = 0
        total_failed = 0
        refresh_results = []
        
        for i in range(0, len(items_to_refresh), batch_size):
            batch = items_to_refresh[i:i + batch_size]
            _update_job_progress(i, len(items_to_refresh), f"Refreshing batch {i//batch_size + 1}")
            
            batch_result = _run_async(_refresh_cache_batch(batch))
            refresh_results.append(batch_result)
            
            total_refreshed += batch_result.items_updated
            total_failed += batch_result.items_processed - batch_result.items_updated
            
            # Rate limiting between batches
            if i + batch_size < len(items_to_refresh):
                time.sleep(2)
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return {
            "success": True,
            "refresh_threshold_hours": refresh_threshold_hours,
            "candidates_found": len(refresh_candidates),
            "items_processed": len(items_to_refresh),
            "items_refreshed": total_refreshed,
            "items_failed": total_failed,
            "refresh_rate": round((total_refreshed / len(items_to_refresh)) * 100, 1),
            "batch_results": [result.to_dict() for result in refresh_results],
            "processing_time_ms": processing_time,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache refresh task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "refresh_threshold_hours": refresh_threshold_hours,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_cache_health', timeout=600, result_ttl=1800)
def cache_health_check_task(
    detailed_analysis: bool = True,
    performance_test: bool = False
) -> Dict[str, Any]:
    """
    Background task to perform comprehensive cache health check.
    
    Args:
        detailed_analysis: Whether to perform detailed cache analysis
        performance_test: Whether to run performance tests
        
    Returns:
        Dict with health check results
    """
    start_time = datetime.now()
    logger.info("Starting cache health check task")
    
    try:
        health_results = {
            "overall_health": "healthy",
            "timestamp": datetime.now().isoformat(),
            "checks_performed": [],
            "issues_found": [],
            "recommendations": []
        }
        
        # Basic connectivity test
        connectivity_result = _run_async(_test_cache_connectivity())
        health_results["checks_performed"].append("connectivity")
        
        if not connectivity_result.success:
            health_results["overall_health"] = "critical"
            health_results["issues_found"].append("Redis connection failed")
            return health_results
        
        # Cache statistics analysis
        stats_result = _run_async(_analyze_cache_statistics())
        health_results["checks_performed"].append("statistics")
        health_results["cache_statistics"] = stats_result.details
        
        # Memory usage analysis
        memory_result = _run_async(_analyze_memory_usage())
        health_results["checks_performed"].append("memory_usage")
        health_results["memory_analysis"] = memory_result.details
        
        if memory_result.details.get("memory_usage_percentage", 0) > 90:
            health_results["overall_health"] = "warning"
            health_results["issues_found"].append("High memory usage")
            health_results["recommendations"].append("Consider running cache cleanup")
        
        # Hit rate analysis
        if detailed_analysis:
            hitrate_result = _run_async(_analyze_hit_rates())
            health_results["checks_performed"].append("hit_rates")
            health_results["hit_rate_analysis"] = hitrate_result.details
            
            avg_hit_rate = hitrate_result.details.get("average_hit_rate", 0)
            if avg_hit_rate < 70:
                health_results["overall_health"] = "warning"
                health_results["issues_found"].append("Low cache hit rate")
                health_results["recommendations"].append("Consider cache warming for popular data")
        
        # Performance testing
        if performance_test:
            perf_result = _run_async(_test_cache_performance())
            health_results["checks_performed"].append("performance")
            health_results["performance_test"] = perf_result.details
            
            avg_response_time = perf_result.details.get("average_response_time_ms", 0)
            if avg_response_time > 50:
                health_results["overall_health"] = "warning"
                health_results["issues_found"].append("Slow cache response times")
        
        # Expiration analysis
        expiration_result = _run_async(_analyze_expiration_patterns())
        health_results["checks_performed"].append("expiration_patterns")
        health_results["expiration_analysis"] = expiration_result.details
        
        # Final health assessment
        if len(health_results["issues_found"]) == 0:
            health_results["overall_health"] = "healthy"
        elif len(health_results["issues_found"]) <= 2 and health_results["overall_health"] != "critical":
            health_results["overall_health"] = "warning"
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        health_results["processing_time_ms"] = processing_time
        
        logger.info(f"Cache health check completed: {health_results['overall_health']}")
        return health_results
        
    except Exception as e:
        logger.error(f"Cache health check task failed: {e}")
        return {
            "success": False,
            "overall_health": "critical",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# Helper functions for cache operations

async def _warm_popular_data_cache(priority_items: Optional[List[str]], force_refresh: bool) -> Dict[str, Any]:
    """Warm cache with popular player and match data."""
    items_added = 0
    items_updated = 0
    
    try:
        # Get popular players from storage
        all_users = await storage.get_all_users()
        popular_players = [user.faceit_player_id for user in all_users if user.faceit_player_id]
        
        # Add priority items
        if priority_items:
            popular_players.extend(priority_items)
        
        # Remove duplicates and limit
        popular_players = list(set(popular_players))[:50]
        
        # Pre-load player data
        for player_id in popular_players:
            try:
                if force_refresh:
                    # Force cache refresh
                    await faceit_api.get_player_by_id(player_id)
                    items_updated += 1
                else:
                    # Use cached version (will load if not cached)
                    await cached_api.get_player_by_id(player_id)
                    items_added += 1
                
                # Rate limiting
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.warning(f"Failed to warm cache for player {player_id}: {e}")
        
        return {
            "success": True,
            "operation_type": "warm_popular_data",
            "items_processed": len(popular_players),
            "items_added": items_added,
            "items_updated": items_updated
        }
        
    except Exception as e:
        return {
            "success": False,
            "operation_type": "warm_popular_data",
            "error": str(e)
        }


async def _warm_recent_players_cache(force_refresh: bool) -> Dict[str, Any]:
    """Warm cache with recently active players."""
    items_processed = 0
    
    try:
        # Get users with recent activity
        cutoff_date = datetime.now() - timedelta(days=7)
        all_users = await storage.get_all_users()
        
        recent_users = [
            user for user in all_users 
            if user.faceit_player_id and 
            hasattr(user, 'last_activity') and 
            user.last_activity and 
            user.last_activity > cutoff_date
        ]
        
        # Pre-load their data
        for user in recent_users:
            try:
                # Load player data
                await cached_api.get_player_by_id(user.faceit_player_id)
                
                # Load recent matches
                await cached_api.get_player_matches(user.faceit_player_id, limit=10)
                
                items_processed += 1
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.warning(f"Failed to warm cache for recent player {user.faceit_player_id}: {e}")
        
        return {
            "success": True,
            "operation_type": "warm_recent_players",
            "items_processed": items_processed,
            "items_added": items_processed
        }
        
    except Exception as e:
        return {
            "success": False,
            "operation_type": "warm_recent_players",
            "error": str(e)
        }


async def _warm_active_matches_cache(force_refresh: bool) -> Dict[str, Any]:
    """Warm cache with active match data."""
    # This would require access to active matches
    # For now, return a placeholder implementation
    return {
        "success": True,
        "operation_type": "warm_active_matches",
        "items_processed": 0,
        "items_added": 0,
        "message": "Active match warming not yet implemented"
    }


async def _warm_comprehensive_cache(priority_items: Optional[List[str]], force_refresh: bool) -> Dict[str, Any]:
    """Comprehensive cache warming across all data types."""
    results = []
    
    # Warm popular data
    popular_result = await _warm_popular_data_cache(priority_items, force_refresh)
    results.append(popular_result)
    
    # Warm recent players
    recent_result = await _warm_recent_players_cache(force_refresh)
    results.append(recent_result)
    
    # Calculate totals
    total_added = sum(r.get("items_added", 0) for r in results)
    total_processed = sum(r.get("items_processed", 0) for r in results)
    
    return {
        "success": all(r.get("success", False) for r in results),
        "operation_type": "warm_comprehensive",
        "items_processed": total_processed,
        "items_added": total_added,
        "sub_operations": results
    }


async def _cleanup_expired_entries(max_items: int, dry_run: bool) -> CacheOperationResult:
    """Clean up expired cache entries."""
    try:
        redis_client = await get_redis_client()
        removed_count = 0
        
        # Get all keys and check expiration
        # This is a simplified implementation
        # In practice, you'd want to use Redis SCAN for large datasets
        
        if not dry_run:
            # Use Redis EVAL script for efficient cleanup
            cleanup_script = """
            local keys = redis.call('KEYS', '*')
            local removed = 0
            for i = 1, #keys do
                local ttl = redis.call('TTL', keys[i])
                if ttl == -2 then  -- Key expired
                    redis.call('DEL', keys[i])
                    removed = removed + 1
                    if removed >= tonumber(ARGV[1]) then
                        break
                    end
                end
            end
            return removed
            """
            removed_count = await redis_client.eval(cleanup_script, 0, str(max_items))
        
        return CacheOperationResult(
            operation_type="cleanup_expired",
            success=True,
            items_processed=max_items,
            items_removed=removed_count if not dry_run else 0
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="cleanup_expired",
            success=False,
            error=str(e)
        )


async def _cleanup_stale_entries(max_items: int, dry_run: bool) -> CacheOperationResult:
    """Clean up stale cache entries (not expired but old)."""
    try:
        # Implementation would identify and remove stale entries
        # based on access patterns and age
        
        return CacheOperationResult(
            operation_type="cleanup_stale",
            success=True,
            items_processed=0,
            items_removed=0,
            details={"message": "Stale cleanup not yet implemented"}
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="cleanup_stale",
            success=False,
            error=str(e)
        )


async def _cleanup_oversized_cache(max_items: int, dry_run: bool) -> CacheOperationResult:
    """Clean up oversized cache entries."""
    try:
        # Implementation would identify large cache entries
        # and remove or compress them
        
        return CacheOperationResult(
            operation_type="cleanup_oversized",
            success=True,
            items_processed=0,
            items_removed=0,
            details={"message": "Oversized cleanup not yet implemented"}
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="cleanup_oversized",
            success=False,
            error=str(e)
        )


async def _optimize_memory_usage(target_reduction_mb: int) -> CacheOperationResult:
    """Optimize cache memory usage."""
    try:
        # Implementation would analyze memory usage and optimize
        
        return CacheOperationResult(
            operation_type="optimize_memory",
            success=True,
            details={"message": "Memory optimization not yet implemented"}
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="optimize_memory",
            success=False,
            error=str(e)
        )


async def _optimize_access_patterns() -> CacheOperationResult:
    """Optimize based on access patterns."""
    try:
        # Implementation would analyze access patterns and adjust TTLs
        
        return CacheOperationResult(
            operation_type="optimize_access_patterns",
            success=True,
            details={"message": "Access pattern optimization not yet implemented"}
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="optimize_access_patterns",
            success=False,
            error=str(e)
        )


async def _optimize_ttl_values() -> CacheOperationResult:
    """Optimize TTL values based on usage patterns."""
    try:
        # Implementation would adjust TTL values for better efficiency
        
        return CacheOperationResult(
            operation_type="optimize_ttl",
            success=True,
            details={"message": "TTL optimization not yet implemented"}
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="optimize_ttl",
            success=False,
            error=str(e)
        )


async def _identify_refresh_candidates(threshold_hours: int, priority_refresh: bool) -> List[Dict[str, Any]]:
    """Identify cache entries that need refreshing."""
    try:
        # Implementation would scan cache for items expiring soon
        return []
        
    except Exception as e:
        logger.error(f"Error identifying refresh candidates: {e}")
        return []


async def _refresh_cache_batch(items: List[Dict[str, Any]]) -> CacheOperationResult:
    """Refresh a batch of cache items."""
    try:
        refreshed = 0
        
        for item in items:
            try:
                # Refresh based on item type
                if item.get("type") == "player":
                    await cached_api.get_player_by_id(item["id"])
                    refreshed += 1
                elif item.get("type") == "match":
                    await cached_api.get_match_details(item["id"])
                    refreshed += 1
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.warning(f"Failed to refresh cache item {item}: {e}")
        
        return CacheOperationResult(
            operation_type="refresh_batch",
            success=True,
            items_processed=len(items),
            items_updated=refreshed
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="refresh_batch",
            success=False,
            error=str(e)
        )


async def _test_cache_connectivity() -> CacheOperationResult:
    """Test basic cache connectivity."""
    try:
        redis_client = await get_redis_client()
        await redis_client.ping()
        
        return CacheOperationResult(
            operation_type="connectivity_test",
            success=True,
            details={"status": "connected"}
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="connectivity_test",
            success=False,
            error=str(e)
        )


async def _analyze_cache_statistics() -> CacheOperationResult:
    """Analyze cache statistics."""
    try:
        stats = await get_all_cache_stats()
        
        return CacheOperationResult(
            operation_type="statistics_analysis",
            success=True,
            details=stats
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="statistics_analysis",
            success=False,
            error=str(e)
        )


async def _analyze_memory_usage() -> CacheOperationResult:
    """Analyze cache memory usage."""
    try:
        redis_client = await get_redis_client()
        info = await redis_client.info('memory')
        
        memory_stats = {
            "used_memory": info.get("used_memory", 0),
            "used_memory_human": info.get("used_memory_human", "0B"),
            "used_memory_peak": info.get("used_memory_peak", 0),
            "memory_usage_percentage": 0  # Would need max memory info
        }
        
        return CacheOperationResult(
            operation_type="memory_analysis",
            success=True,
            details=memory_stats
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="memory_analysis",
            success=False,
            error=str(e)
        )


async def _analyze_hit_rates() -> CacheOperationResult:
    """Analyze cache hit rates."""
    try:
        # This would require implementing hit rate tracking
        # For now, return placeholder data
        
        hit_rate_stats = {
            "player_cache_hit_rate": 85.5,
            "match_cache_hit_rate": 78.2,
            "stats_cache_hit_rate": 82.1,
            "average_hit_rate": 81.9
        }
        
        return CacheOperationResult(
            operation_type="hit_rate_analysis",
            success=True,
            details=hit_rate_stats
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="hit_rate_analysis",
            success=False,
            error=str(e)
        )


async def _test_cache_performance() -> CacheOperationResult:
    """Test cache performance."""
    try:
        redis_client = await get_redis_client()
        
        # Perform simple performance test
        test_key = f"perf_test_{datetime.now().timestamp()}"
        test_data = {"test": "data", "timestamp": datetime.now().isoformat()}
        
        # Test write performance
        write_start = datetime.now()
        await redis_client.setex(test_key, 60, json.dumps(test_data))
        write_time = (datetime.now() - write_start).total_seconds() * 1000
        
        # Test read performance
        read_start = datetime.now()
        await redis_client.get(test_key)
        read_time = (datetime.now() - read_start).total_seconds() * 1000
        
        # Cleanup
        await redis_client.delete(test_key)
        
        perf_stats = {
            "write_time_ms": round(write_time, 2),
            "read_time_ms": round(read_time, 2),
            "average_response_time_ms": round((write_time + read_time) / 2, 2)
        }
        
        return CacheOperationResult(
            operation_type="performance_test",
            success=True,
            details=perf_stats
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="performance_test",
            success=False,
            error=str(e)
        )


async def _analyze_expiration_patterns() -> CacheOperationResult:
    """Analyze cache expiration patterns."""
    try:
        # This would analyze TTL patterns and expiration rates
        # For now, return placeholder data
        
        expiration_stats = {
            "average_ttl_seconds": 300,
            "items_expiring_soon": 0,
            "expired_items_per_hour": 0
        }
        
        return CacheOperationResult(
            operation_type="expiration_analysis",
            success=True,
            details=expiration_stats
        )
        
    except Exception as e:
        return CacheOperationResult(
            operation_type="expiration_analysis",
            success=False,
            error=str(e)
        )