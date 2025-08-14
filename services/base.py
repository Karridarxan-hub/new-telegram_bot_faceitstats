"""
Base Service implementation with common patterns.

Provides abstract base class for all services with:
- Repository management and injection
- Transaction handling and rollback
- Event publishing and coordination
- Error handling and logging
- Cache management integration
- Business rule validation
- Performance monitoring
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypeVar, Generic, Union, Callable
from datetime import datetime
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
import asyncio
import uuid
import time

from sqlalchemy.ext.asyncio import AsyncSession
from database.connection import get_db_session, DatabaseOperationError
from utils.redis_cache import RedisCache

logger = logging.getLogger(__name__)

# Type variables for generic service operations
T = TypeVar("T")
ServiceResultType = TypeVar("ServiceResultType")


class ServiceError(Exception):
    """Base exception for service layer errors."""
    
    def __init__(
        self,
        message: str,
        error_code: str = "SERVICE_ERROR",
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.cause = cause
        self.timestamp = datetime.now()
        super().__init__(message)


class ValidationError(ServiceError):
    """Validation error in service operation."""
    
    def __init__(self, message: str, field: str = None, details: Optional[Dict[str, Any]] = None):
        self.field = field
        super().__init__(message, "VALIDATION_ERROR", details)


class BusinessRuleError(ServiceError):
    """Business rule violation error."""
    
    def __init__(self, message: str, rule: str, details: Optional[Dict[str, Any]] = None):
        self.rule = rule
        super().__init__(message, "BUSINESS_RULE_ERROR", details)


class PermissionError(ServiceError):
    """Permission denied error."""
    
    def __init__(self, message: str, required_permission: str = None):
        self.required_permission = required_permission
        super().__init__(message, "PERMISSION_ERROR")


class RateLimitError(ServiceError):
    """Rate limit exceeded error."""
    
    def __init__(self, message: str, retry_after: Optional[int] = None):
        self.retry_after = retry_after
        super().__init__(message, "RATE_LIMIT_ERROR", {"retry_after": retry_after})


@dataclass
class ServiceResult(Generic[ServiceResultType]):
    """Standard result wrapper for service operations."""
    
    success: bool
    data: Optional[ServiceResultType] = None
    error: Optional[ServiceError] = None
    metadata: Optional[Dict[str, Any]] = None
    processing_time_ms: Optional[int] = None
    
    @classmethod
    def success_result(
        cls,
        data: ServiceResultType,
        metadata: Optional[Dict[str, Any]] = None,
        processing_time_ms: Optional[int] = None
    ) -> "ServiceResult[ServiceResultType]":
        """Create successful result."""
        return cls(
            success=True,
            data=data,
            metadata=metadata or {},
            processing_time_ms=processing_time_ms
        )
    
    @classmethod
    def error_result(
        cls,
        error: ServiceError,
        metadata: Optional[Dict[str, Any]] = None
    ) -> "ServiceResult[ServiceResultType]":
        """Create error result."""
        return cls(
            success=False,
            error=error,
            metadata=metadata or {}
        )
    
    @classmethod
    def validation_error(
        cls,
        message: str,
        field: str = None,
        details: Optional[Dict[str, Any]] = None
    ) -> "ServiceResult[ServiceResultType]":
        """Create validation error result."""
        return cls.error_result(ValidationError(message, field, details))
    
    @classmethod
    def business_rule_error(
        cls,
        message: str,
        rule: str,
        details: Optional[Dict[str, Any]] = None
    ) -> "ServiceResult[ServiceResultType]":
        """Create business rule error result."""
        return cls.error_result(BusinessRuleError(message, rule, details))
    
    @classmethod
    def permission_error(
        cls,
        message: str,
        required_permission: str = None
    ) -> "ServiceResult[ServiceResultType]":
        """Create permission error result."""
        return cls.error_result(PermissionError(message, required_permission))


class EventType(Enum):
    """Event types for service coordination."""
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    SUBSCRIPTION_UPGRADED = "subscription_upgraded"
    SUBSCRIPTION_EXPIRED = "subscription_expired"
    MATCH_ANALYZED = "match_analyzed"
    PAYMENT_COMPLETED = "payment_completed"
    PAYMENT_FAILED = "payment_failed"
    CACHE_CLEARED = "cache_cleared"


@dataclass
class ServiceEvent:
    """Event data structure for inter-service communication."""
    
    event_type: EventType
    entity_id: Union[str, uuid.UUID, int]
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    timestamp: datetime
    correlation_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.correlation_id:
            self.correlation_id = str(uuid.uuid4())


class EventBus:
    """Simple event bus for service coordination."""
    
    def __init__(self):
        self._handlers: Dict[EventType, List[Callable]] = {}
        self._lock = asyncio.Lock()
    
    async def subscribe(self, event_type: EventType, handler: Callable):
        """Subscribe to event type."""
        async with self._lock:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)
    
    async def publish(self, event: ServiceEvent):
        """Publish event to subscribers."""
        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            return
        
        # Execute handlers in background to avoid blocking
        tasks = []
        for handler in handlers:
            task = asyncio.create_task(self._safe_handler_execution(handler, event))
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _safe_handler_execution(self, handler: Callable, event: ServiceEvent):
        """Safely execute event handler with error handling."""
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception as e:
            logger.error(f"Event handler error for {event.event_type}: {e}")


# Global event bus instance
event_bus = EventBus()


class BaseService(ABC):
    """
    Abstract base service with common functionality.
    
    Provides:
    - Repository dependency injection
    - Transaction management
    - Event publishing
    - Cache coordination
    - Error handling patterns
    - Performance monitoring
    - Business rule validation
    """
    
    def __init__(self, cache: Optional[RedisCache] = None):
        """
        Initialize service with optional cache.
        
        Args:
            cache: Optional Redis cache instance
        """
        self.cache = cache
        self._repositories: Dict[str, Any] = {}
        self._event_bus = event_bus
        self._performance_metrics: Dict[str, List[float]] = {}
    
    def register_repository(self, name: str, repository: Any):
        """
        Register repository for dependency injection.
        
        Args:
            name: Repository name for lookup
            repository: Repository instance
        """
        self._repositories[name] = repository
        logger.debug(f"Registered repository '{name}' in {self.__class__.__name__}")
    
    def get_repository(self, name: str) -> Any:
        """
        Get registered repository by name.
        
        Args:
            name: Repository name
            
        Returns:
            Repository instance
            
        Raises:
            ValueError: If repository not found
        """
        if name not in self._repositories:
            raise ValueError(f"Repository '{name}' not registered in {self.__class__.__name__}")
        return self._repositories[name]
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session with transaction management."""
        async with get_db_session() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Service transaction rolled back: {e}")
                raise
    
    async def measure_performance(self, operation_name: str, func: Callable, *args, **kwargs):
        """
        Measure and track operation performance.
        
        Args:
            operation_name: Name of the operation being measured
            func: Function to execute and measure
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result and execution time
        """
        start_time = time.time()
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            execution_time = (time.time() - start_time) * 1000  # Convert to milliseconds
            
            # Track performance metrics
            if operation_name not in self._performance_metrics:
                self._performance_metrics[operation_name] = []
            
            self._performance_metrics[operation_name].append(execution_time)
            
            # Keep only last 100 measurements
            if len(self._performance_metrics[operation_name]) > 100:
                self._performance_metrics[operation_name] = self._performance_metrics[operation_name][-100:]
            
            logger.debug(f"{self.__class__.__name__}.{operation_name} completed in {execution_time:.2f}ms")
            
            return result, int(execution_time)
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"{self.__class__.__name__}.{operation_name} failed after {execution_time:.2f}ms: {e}")
            raise
    
    async def publish_event(
        self,
        event_type: EventType,
        entity_id: Union[str, uuid.UUID, int],
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Publish service event to event bus.
        
        Args:
            event_type: Type of event
            entity_id: ID of affected entity
            data: Event data
            metadata: Optional metadata
        """
        event = ServiceEvent(
            event_type=event_type,
            entity_id=entity_id,
            data=data,
            metadata=metadata or {},
            timestamp=datetime.now()
        )
        
        try:
            await self._event_bus.publish(event)
        except Exception as e:
            logger.error(f"Failed to publish event {event_type}: {e}")
    
    def validate_required_fields(self, data: Dict[str, Any], required_fields: List[str]):
        """
        Validate required fields in data.
        
        Args:
            data: Data to validate
            required_fields: List of required field names
            
        Raises:
            ValidationError: If required field is missing
        """
        missing_fields = []
        for field in required_fields:
            if field not in data or data[field] is None:
                missing_fields.append(field)
        
        if missing_fields:
            raise ValidationError(
                f"Missing required fields: {', '.join(missing_fields)}",
                field=missing_fields[0],
                details={"missing_fields": missing_fields}
            )
    
    def validate_field_constraints(
        self,
        data: Dict[str, Any],
        constraints: Dict[str, Dict[str, Any]]
    ):
        """
        Validate field constraints.
        
        Args:
            data: Data to validate
            constraints: Dictionary of field constraints
                Example: {"email": {"type": str, "max_length": 100}}
            
        Raises:
            ValidationError: If constraint is violated
        """
        for field_name, field_constraints in constraints.items():
            if field_name not in data:
                continue
            
            value = data[field_name]
            
            # Type validation
            if "type" in field_constraints:
                expected_type = field_constraints["type"]
                if not isinstance(value, expected_type):
                    raise ValidationError(
                        f"Field '{field_name}' must be of type {expected_type.__name__}",
                        field=field_name
                    )
            
            # Length constraints
            if isinstance(value, str):
                if "min_length" in field_constraints:
                    min_length = field_constraints["min_length"]
                    if len(value) < min_length:
                        raise ValidationError(
                            f"Field '{field_name}' must be at least {min_length} characters long",
                            field=field_name
                        )
                
                if "max_length" in field_constraints:
                    max_length = field_constraints["max_length"]
                    if len(value) > max_length:
                        raise ValidationError(
                            f"Field '{field_name}' must be at most {max_length} characters long",
                            field=field_name
                        )
            
            # Range constraints
            if isinstance(value, (int, float)):
                if "min_value" in field_constraints:
                    min_value = field_constraints["min_value"]
                    if value < min_value:
                        raise ValidationError(
                            f"Field '{field_name}' must be at least {min_value}",
                            field=field_name
                        )
                
                if "max_value" in field_constraints:
                    max_value = field_constraints["max_value"]
                    if value > max_value:
                        raise ValidationError(
                            f"Field '{field_name}' must be at most {max_value}",
                            field=field_name
                        )
    
    async def with_cache(
        self,
        cache_key: str,
        fetch_func: Callable,
        ttl: int = 300,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with caching support.
        
        Args:
            cache_key: Cache key for storing result
            fetch_func: Function to execute if cache miss
            ttl: Time to live in seconds
            *args: Arguments for fetch_func
            **kwargs: Keyword arguments for fetch_func
            
        Returns:
            Cached or freshly fetched result
        """
        if not self.cache:
            if asyncio.iscoroutinefunction(fetch_func):
                return await fetch_func(*args, **kwargs)
            else:
                return fetch_func(*args, **kwargs)
        
        try:
            # Try to get from cache
            cached_result = await self.cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for key: {cache_key}")
                return cached_result
        except Exception as e:
            logger.warning(f"Cache get error for key {cache_key}: {e}")
        
        # Cache miss - fetch fresh data
        try:
            if asyncio.iscoroutinefunction(fetch_func):
                result = await fetch_func(*args, **kwargs)
            else:
                result = fetch_func(*args, **kwargs)
            
            # Store in cache
            try:
                await self.cache.set(cache_key, result, ttl)
                logger.debug(f"Cached result for key: {cache_key}")
            except Exception as e:
                logger.warning(f"Cache set error for key {cache_key}: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to fetch data for cache key {cache_key}: {e}")
            raise
    
    async def invalidate_cache_pattern(self, pattern: str):
        """
        Invalidate cache entries matching pattern.
        
        Args:
            pattern: Cache key pattern to invalidate
        """
        if not self.cache:
            return
        
        try:
            keys = await self.cache.get_keys_pattern(pattern)
            for key in keys:
                await self.cache.delete(key)
            logger.debug(f"Invalidated {len(keys)} cache entries matching pattern: {pattern}")
        except Exception as e:
            logger.warning(f"Cache invalidation error for pattern {pattern}: {e}")
    
    def get_performance_metrics(self) -> Dict[str, Dict[str, float]]:
        """
        Get performance metrics for this service.
        
        Returns:
            Dictionary with performance statistics
        """
        metrics = {}
        
        for operation_name, times in self._performance_metrics.items():
            if not times:
                continue
            
            metrics[operation_name] = {
                "count": len(times),
                "avg_ms": round(sum(times) / len(times), 2),
                "min_ms": round(min(times), 2),
                "max_ms": round(max(times), 2),
                "total_ms": round(sum(times), 2)
            }
        
        return metrics
    
    @abstractmethod
    async def health_check(self) -> ServiceResult[Dict[str, Any]]:
        """
        Perform service health check.
        
        Returns:
            ServiceResult with health status
        """
        pass
    
    async def _base_health_check(self) -> Dict[str, Any]:
        """Base health check implementation."""
        health_data = {
            "service": self.__class__.__name__,
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "repositories": list(self._repositories.keys()),
            "performance_metrics": self.get_performance_metrics()
        }
        
        # Check cache connectivity if available
        if self.cache:
            try:
                await self.cache.ping()
                health_data["cache_status"] = "connected"
            except Exception as e:
                health_data["cache_status"] = f"error: {e}"
                health_data["status"] = "degraded"
        
        return health_data