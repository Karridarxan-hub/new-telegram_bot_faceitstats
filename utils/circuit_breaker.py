"""Circuit breaker pattern implementation for external API calls."""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Any, Optional
from functools import wraps

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker for external service calls."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: Exception = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED
        
    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset the circuit."""
        return (
            self.state == CircuitState.OPEN and
            self.last_failure_time and
            datetime.now() - self.last_failure_time > timedelta(seconds=self.recovery_timeout)
        )
    
    def _record_success(self):
        """Record successful operation."""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        logger.info("Circuit breaker reset - service recovered")
    
    def _record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            if self.state == CircuitState.CLOSED:
                self.state = CircuitState.OPEN
                logger.warning(f"Circuit breaker opened - {self.failure_count} failures reached threshold")
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning("Circuit breaker opened again - half-open test failed")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        # Check if we should attempt reset
        if self._should_attempt_reset():
            self.state = CircuitState.HALF_OPEN
            logger.info("Circuit breaker half-open - testing service")
        
        # Reject if circuit is open
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerOpenError("Circuit breaker is open")
        
        try:
            result = await func(*args, **kwargs)
            self._record_success()
            return result
        except self.expected_exception as e:
            self._record_failure()
            raise e


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: Exception = Exception
):
    """Decorator to add circuit breaker functionality to functions."""
    def decorator(func):
        breaker = CircuitBreaker(failure_threshold, recovery_timeout, expected_exception)
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        
        wrapper._circuit_breaker = breaker  # For testing/monitoring
        return wrapper
    
    return decorator


class AdaptiveTimeout:
    """Adaptive timeout that adjusts based on response times."""
    
    def __init__(self, base_timeout: float = 30.0, max_timeout: float = 120.0):
        self.base_timeout = base_timeout
        self.max_timeout = max_timeout
        self.recent_times: list[float] = []
        self.max_samples = 10
    
    def add_response_time(self, response_time: float):
        """Add a response time sample."""
        self.recent_times.append(response_time)
        if len(self.recent_times) > self.max_samples:
            self.recent_times.pop(0)
    
    def get_timeout(self) -> float:
        """Get adaptive timeout based on recent response times."""
        if not self.recent_times:
            return self.base_timeout
        
        avg_time = sum(self.recent_times) / len(self.recent_times)
        # Set timeout to 3x average response time, but within bounds
        adaptive_timeout = min(avg_time * 3, self.max_timeout)
        return max(adaptive_timeout, self.base_timeout)


class PerformanceMonitor:
    """Monitor performance metrics for API calls."""
    
    def __init__(self):
        self.call_times: dict[str, list[float]] = {}
        self.error_counts: dict[str, int] = {}
        self.success_counts: dict[str, int] = {}
    
    def record_call(self, endpoint: str, duration: float, success: bool):
        """Record API call performance."""
        if endpoint not in self.call_times:
            self.call_times[endpoint] = []
            self.error_counts[endpoint] = 0
            self.success_counts[endpoint] = 0
        
        self.call_times[endpoint].append(duration)
        if len(self.call_times[endpoint]) > 100:  # Keep last 100 samples
            self.call_times[endpoint].pop(0)
        
        if success:
            self.success_counts[endpoint] += 1
        else:
            self.error_counts[endpoint] += 1
    
    def get_stats(self, endpoint: str) -> dict:
        """Get performance statistics for an endpoint."""
        times = self.call_times.get(endpoint, [])
        if not times:
            return {"avg_time": 0, "success_rate": 0, "total_calls": 0}
        
        total_calls = self.success_counts.get(endpoint, 0) + self.error_counts.get(endpoint, 0)
        success_rate = self.success_counts.get(endpoint, 0) / total_calls if total_calls > 0 else 0
        
        return {
            "avg_time": sum(times) / len(times),
            "min_time": min(times),
            "max_time": max(times),
            "success_rate": success_rate,
            "total_calls": total_calls
        }
    
    def get_all_stats(self) -> dict:
        """Get performance statistics for all endpoints."""
        return {endpoint: self.get_stats(endpoint) for endpoint in self.call_times.keys()}


# Global performance monitor instance
performance_monitor = PerformanceMonitor()