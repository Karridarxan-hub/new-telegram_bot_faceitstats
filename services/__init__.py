"""
Service Layer for FACEIT Telegram Bot.

This package provides the business logic layer that orchestrates between
repositories, external APIs, and bot handlers. Services implement business
rules, validation, transaction management, and event coordination.

Architecture:
- BaseService: Abstract service class with common patterns
- UserService: User management and FACEIT integration
- SubscriptionService: Subscription management and payments
- MatchService: Match analysis and processing
- AnalyticsService: Metrics and reporting
- CacheService: Unified cache management

Key Features:
- Repository pattern integration
- Business rule validation
- Transaction management
- Redis cache orchestration
- Event-driven updates
- Comprehensive error handling
"""

from .base import BaseService, ServiceResult, ServiceError
from .user import UserService
from .subscription import SubscriptionService
from .match import MatchService
from .analytics import AnalyticsService
from .cache import CacheService

__all__ = [
    'BaseService',
    'ServiceResult',
    'ServiceError',
    'UserService',
    'SubscriptionService',
    'MatchService',
    'AnalyticsService',
    'CacheService',
]

# Service version for compatibility tracking
SERVICE_VERSION = "1.0.0"