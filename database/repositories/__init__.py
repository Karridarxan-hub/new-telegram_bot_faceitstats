"""
Repository pattern implementations for FACEIT Telegram Bot.

This module provides data access layer abstractions for PostgreSQL
using async SQLAlchemy 2.0 patterns with Redis cache integration.

Repositories:
- BaseRepository: Abstract base class with common CRUD operations
- UserRepository: User management with FACEIT integration  
- SubscriptionRepository: Subscription and payment management
- MatchRepository: Match analysis and caching
- StatsRepository: Player statistics caching
- AnalyticsRepository: Usage metrics and analytics

Features:
- Async/await patterns throughout
- Comprehensive error handling and logging
- Filtering, pagination, and sorting
- Batch operations for performance
- Relationship management
- Redis cache integration
- Database transaction management
- Type hints and documentation
"""

from .base import BaseRepository
from .user import UserRepository
from .subscription import SubscriptionRepository
from .match import MatchRepository
from .stats import StatsRepository
from .analytics import AnalyticsRepository

__all__ = [
    'BaseRepository',
    'UserRepository', 
    'SubscriptionRepository',
    'MatchRepository',
    'StatsRepository',
    'AnalyticsRepository',
]