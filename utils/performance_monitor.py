"""Performance monitoring and health checks for the FACEIT bot."""

import asyncio
import time
import logging
import psutil
import gc
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics container."""
    timestamp: datetime
    response_time: float
    memory_usage: float  # MB
    cpu_usage: float    # percentage
    cache_hit_rate: float
    active_connections: int
    error_count: int = 0
    success_count: int = 0


class PerformanceMonitor:
    """Real-time performance monitoring system."""
    
    def __init__(self, max_samples: int = 1000):
        self.max_samples = max_samples
        self.metrics_history: deque = deque(maxlen=max_samples)
        self.endpoint_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total_calls": 0,
            "success_calls": 0,
            "error_calls": 0,
            "total_time": 0.0,
            "min_time": float('inf'),
            "max_time": 0.0,
            "last_call": None
        })
        self.process = psutil.Process()
        self.start_time = time.time()
        
    def record_api_call(self, endpoint: str, duration: float, success: bool = True):
        """Record API call performance."""
        stats = self.endpoint_stats[endpoint]
        stats["total_calls"] += 1
        stats["total_time"] += duration
        stats["last_call"] = datetime.now()
        
        if success:
            stats["success_calls"] += 1
        else:
            stats["error_calls"] += 1
            
        # Update min/max times
        stats["min_time"] = min(stats["min_time"], duration)
        stats["max_time"] = max(stats["max_time"], duration)
        
        # Add to global metrics
        try:
            memory_mb = self.process.memory_info().rss / 1024 / 1024
            cpu_percent = self.process.cpu_percent()
            
            metrics = PerformanceMetrics(
                timestamp=datetime.now(),
                response_time=duration,
                memory_usage=memory_mb,
                cpu_usage=cpu_percent,
                cache_hit_rate=0.0,  # Will be updated separately
                active_connections=0,  # Will be updated separately
                success_count=1 if success else 0,
                error_count=0 if success else 1
            )
            
            self.metrics_history.append(metrics)
            
        except Exception as e:
            logger.error(f"Error recording performance metrics: {e}")
    
    def get_endpoint_stats(self, endpoint: str) -> Dict[str, Any]:
        """Get statistics for a specific endpoint."""
        stats = self.endpoint_stats[endpoint]
        if stats["total_calls"] == 0:
            return {"message": "No calls recorded"}
            
        avg_time = stats["total_time"] / stats["total_calls"]
        success_rate = stats["success_calls"] / stats["total_calls"] * 100
        
        return {
            "total_calls": stats["total_calls"],
            "success_rate": f"{success_rate:.1f}%",
            "avg_response_time": f"{avg_time:.2f}s",
            "min_response_time": f"{stats['min_time']:.2f}s",
            "max_response_time": f"{stats['max_time']:.2f}s",
            "last_call": stats["last_call"].strftime("%Y-%m-%d %H:%M:%S") if stats["last_call"] else "Never"
        }
    
    def get_overall_health(self) -> Dict[str, Any]:
        """Get overall system health metrics."""
        if not self.metrics_history:
            return {"status": "No data", "uptime": self.get_uptime()}
            
        # Calculate recent metrics (last 5 minutes)
        five_min_ago = datetime.now() - timedelta(minutes=5)
        recent_metrics = [m for m in self.metrics_history if m.timestamp > five_min_ago]
        
        if not recent_metrics:
            recent_metrics = list(self.metrics_history)[-10:]  # Last 10 if no recent data
            
        # System health
        try:
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            cpu_percent = self.process.cpu_percent()
            
            # Calculate averages
            avg_response_time = sum(m.response_time for m in recent_metrics) / len(recent_metrics)
            avg_memory = sum(m.memory_usage for m in recent_metrics) / len(recent_metrics)
            total_success = sum(m.success_count for m in recent_metrics)
            total_errors = sum(m.error_count for m in recent_metrics)
            
            success_rate = (total_success / (total_success + total_errors) * 100) if (total_success + total_errors) > 0 else 100
            
            # Health status
            status = "Healthy"
            if avg_response_time > 5.0:
                status = "Slow"
            elif total_errors > total_success * 0.1:  # More than 10% error rate
                status = "Degraded"
            elif memory_mb > 500:  # More than 500MB
                status = "High Memory"
                
            return {
                "status": status,
                "uptime": self.get_uptime(),
                "memory_usage_mb": f"{memory_mb:.1f}",
                "cpu_usage_percent": f"{cpu_percent:.1f}",
                "avg_response_time": f"{avg_response_time:.2f}s",
                "success_rate": f"{success_rate:.1f}%",
                "total_requests": len(self.metrics_history),
                "recent_requests": len(recent_metrics),
                "garbage_collections": gc.get_count()
            }
            
        except Exception as e:
            logger.error(f"Error getting health metrics: {e}")
            return {"status": "Error", "error": str(e)}
    
    def get_uptime(self) -> str:
        """Get formatted uptime."""
        uptime_seconds = time.time() - self.start_time
        uptime_delta = timedelta(seconds=int(uptime_seconds))
        return str(uptime_delta)
    
    def get_top_slow_endpoints(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get top slowest endpoints."""
        endpoint_avgs = []
        
        for endpoint, stats in self.endpoint_stats.items():
            if stats["total_calls"] > 0:
                avg_time = stats["total_time"] / stats["total_calls"]
                endpoint_avgs.append({
                    "endpoint": endpoint,
                    "avg_time": avg_time,
                    "calls": stats["total_calls"]
                })
        
        # Sort by average time descending
        endpoint_avgs.sort(key=lambda x: x["avg_time"], reverse=True)
        return endpoint_avgs[:limit]
    
    def cleanup_old_metrics(self, hours: int = 24):
        """Clean up old metrics to prevent memory buildup."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Keep only recent metrics
        self.metrics_history = deque(
            [m for m in self.metrics_history if m.timestamp > cutoff_time],
            maxlen=self.max_samples
        )
        
        # Force garbage collection
        gc.collect()
        logger.info(f"Cleaned up metrics older than {hours} hours. Current samples: {len(self.metrics_history)}")


class HealthChecker:
    """Health check utilities."""
    
    def __init__(self, performance_monitor: PerformanceMonitor):
        self.monitor = performance_monitor
        
    async def check_faceit_api_health(self, faceit_api) -> Dict[str, Any]:
        """Check FACEIT API health."""
        try:
            start_time = time.time()
            
            # Try to search for a known player (s1mple)
            player = await faceit_api.search_player("s1mple")
            
            duration = time.time() - start_time
            
            if player:
                return {
                    "status": "healthy",
                    "response_time": f"{duration:.2f}s",
                    "message": "API responding normally"
                }
            else:
                return {
                    "status": "degraded", 
                    "response_time": f"{duration:.2f}s",
                    "message": "API responding but data issues"
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "message": "API not accessible"
            }
    
    async def check_redis_health(self, redis_cache) -> Dict[str, Any]:
        """Check Redis cache health."""
        try:
            if hasattr(redis_cache, 'is_connected') and redis_cache.is_connected():
                stats = await redis_cache.get_stats()
                return {
                    "status": "healthy",
                    "connected": True,
                    "hit_rate": f"{stats.get('hit_rate', 0)}%",
                    "memory_used": stats.get('memory_used', 'N/A')
                }
            else:
                return {
                    "status": "unhealthy",
                    "connected": False,
                    "message": "Redis not connected"
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "message": "Redis health check failed"
            }
    
    def get_comprehensive_health_report(self) -> Dict[str, Any]:
        """Get comprehensive health report."""
        return {
            "system": self.monitor.get_overall_health(),
            "slow_endpoints": self.monitor.get_top_slow_endpoints(),
            "timestamp": datetime.now().isoformat(),
            "recommendations": self._get_performance_recommendations()
        }
    
    def _get_performance_recommendations(self) -> List[str]:
        """Get performance recommendations based on metrics."""
        recommendations = []
        health = self.monitor.get_overall_health()
        
        try:
            memory_mb = float(health.get("memory_usage_mb", "0").replace("MB", ""))
            if memory_mb > 300:
                recommendations.append("Consider implementing memory cleanup or reducing cache sizes")
                
            avg_time = float(health.get("avg_response_time", "0s").replace("s", ""))
            if avg_time > 3.0:
                recommendations.append("API response times are high - check network connectivity and cache effectiveness")
                
            success_rate = float(health.get("success_rate", "100%").replace("%", ""))
            if success_rate < 95:
                recommendations.append("High error rate detected - review error logs and implement better error handling")
                
            if not recommendations:
                recommendations.append("System performance is optimal")
                
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            recommendations.append("Unable to generate recommendations - check logs")
            
        return recommendations


# Global performance monitor instance
performance_monitor = PerformanceMonitor()
health_checker = HealthChecker(performance_monitor)


def performance_tracker(endpoint_name: str):
    """Decorator to track function performance."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            success = False
            try:
                result = await func(*args, **kwargs)
                success = True
                return result
            except Exception as e:
                logger.error(f"Error in {endpoint_name}: {e}")
                raise
            finally:
                duration = time.time() - start_time
                performance_monitor.record_api_call(endpoint_name, duration, success)
        return wrapper
    return decorator