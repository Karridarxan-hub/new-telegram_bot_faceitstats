# FACEIT Telegram Bot - Repository Pattern Implementation

## Overview

This implementation provides a comprehensive Repository pattern for the FACEIT Telegram Bot PostgreSQL migration, replacing the current JSON-based storage with a robust, scalable database solution integrated with Redis caching.

## Architecture

### Repository Structure

```
database/repositories/
├── __init__.py           # Module exports
├── base.py              # Abstract base repository
├── user.py              # User management
├── subscription.py      # Subscription and payments  
├── match.py            # Match analysis and caching
├── stats.py            # Player statistics caching
└── analytics.py        # Usage metrics and analytics
```

### Key Features

- **Async/Await Patterns**: Full async support with SQLAlchemy 2.0
- **Redis Cache Integration**: Multi-level caching with TTL management
- **Comprehensive Error Handling**: Robust error handling and logging
- **Batch Operations**: Optimized bulk operations for performance
- **Relationship Management**: Proper handling of model relationships
- **Type Safety**: Full type hints and generic support
- **Transaction Management**: Automatic transaction handling
- **Performance Optimization**: Indexing, pagination, and query optimization

## Repository Classes

### 1. BaseRepository

**Purpose**: Abstract base class providing common CRUD operations

**Key Features**:
- Generic type support for models and schemas
- Automatic Redis caching with configurable TTL
- Transaction management with rollback support
- Batch operations (create, update, delete)
- Advanced filtering, sorting, and pagination
- Relationship eager loading
- Statistics and analytics methods

**Methods**:
```python
# Core CRUD
async def get_by_id(id) -> Optional[ModelType]
async def get_all(skip, limit, filters) -> List[ModelType]
async def create(obj_in) -> ModelType
async def update(id, obj_in) -> Optional[ModelType]
async def delete(id) -> bool

# Batch operations
async def create_batch(objects) -> List[ModelType]
async def update_batch(updates) -> int
async def delete_batch(ids) -> int

# Utilities
async def count(filters) -> int
async def exists(id) -> bool
async def find_one(filters) -> Optional[ModelType]
```

### 2. UserRepository

**Purpose**: User management with FACEIT integration

**Key Features**:
- Telegram user ID to database UUID mapping
- FACEIT account linking and unlinking
- Activity tracking and analytics
- User search and filtering
- Relationship management with subscriptions and matches

**Specialized Methods**:
```python
async def get_by_telegram_id(user_id) -> Optional[User]
async def get_by_faceit_id(faceit_player_id) -> Optional[User]
async def create_user(user_id, faceit_data) -> User
async def link_faceit_account(user_id, faceit_data) -> Optional[User]
async def get_users_with_faceit_accounts() -> List[User]
async def get_user_stats() -> Dict[str, Any]
```

### 3. SubscriptionRepository & PaymentRepository

**Purpose**: Subscription and payment management

**Key Features**:
- Subscription tier management and upgrades
- Payment processing and history tracking
- Referral system with automatic bonuses
- Usage limits and rate limiting
- Subscription expiration handling
- Revenue analytics and reporting

**Specialized Methods**:
```python
# Subscription management
async def upgrade_subscription(user_id, tier, duration) -> Optional[UserSubscription]
async def can_make_request(user_id) -> Tuple[bool, Dict]
async def check_and_expire_subscriptions() -> List[UserSubscription]
async def apply_referral(user_id, code) -> Tuple[bool, Optional[str]]

# Payment processing
async def create_payment(user_id, amount, tier) -> Payment
async def complete_payment(payment_id, charge_id) -> Optional[Payment]
async def get_revenue_stats() -> Dict[str, Any]
```

### 4. MatchRepository & MatchCacheRepository

**Purpose**: Match analysis and data caching

**Key Features**:
- Match analysis history tracking
- FACEIT API response caching
- Performance metrics and statistics
- Match status updates and monitoring
- Popular match tracking
- Cache cleanup and optimization

**Specialized Methods**:
```python
# Match analysis
async def create_analysis(user_id, match_id, data) -> MatchAnalysis
async def get_by_match_id(match_id) -> Optional[MatchAnalysis]
async def update_match_status(match_id, status) -> List[MatchAnalysis]
async def get_popular_matches() -> List[Dict]

# Cache management
async def cache_match_data(match_id, data, ttl) -> MatchCache
async def get_cached_match(match_id) -> Optional[MatchCache]
async def cleanup_expired_cache() -> int
```

### 5. StatsRepository

**Purpose**: Player statistics caching and analytics

**Key Features**:
- Player performance tracking and caching
- HLTV rating calculations and trends
- Map-specific performance analytics
- Team analysis and comparisons
- Skill-based player rankings
- Weapon and clutch statistics

**Specialized Methods**:
```python
# Player statistics
async def get_player_stats(player_id) -> Optional[PlayerStatsCache]
async def cache_player_stats(player_id, stats_data) -> PlayerStatsCache
async def get_team_stats(player_ids) -> List[PlayerStatsCache]

# Analytics
async def get_top_players_by_rating() -> List[PlayerStatsCache]
async def analyze_player_trends(player_id) -> Dict[str, Any]
async def get_map_performance_stats(map_name) -> Dict[str, Any]
```

### 6. AnalyticsRepository

**Purpose**: Usage metrics and business analytics

**Key Features**:
- Metrics collection and aggregation
- User behavior analytics
- Performance monitoring
- Revenue and business intelligence
- Real-time dashboard data
- System health monitoring

**Specialized Methods**:
```python
# Metrics collection
async def record_metric(name, value, type) -> Analytics
async def record_batch_metrics(metrics) -> List[Analytics]

# Analytics
async def get_user_activity_metrics() -> Dict[str, Any]
async def get_performance_metrics() -> Dict[str, Any]
async def get_revenue_analytics() -> Dict[str, Any]
async def get_realtime_dashboard() -> Dict[str, Any]
```

## Redis Cache Integration

### Cache Strategy

1. **Multi-Level Caching**:
   - Redis for fast access patterns
   - PostgreSQL for persistent storage
   - Application-level result caching

2. **Cache Types**:
   - `player_cache`: Player statistics (5 min TTL)
   - `match_cache`: Match data (2 min TTL)  
   - `stats_cache`: Aggregated statistics (10 min TTL)

3. **Cache Keys**:
   - Consistent key naming: `{table}:{operation}:{identifier}`
   - Pattern-based invalidation support
   - Automatic TTL management

### Cache Methods

```python
# Base cache operations
async def _get_from_cache(key) -> Optional[Any]
async def _set_cache(key, value, ttl) -> None
async def _invalidate_cache(pattern) -> None

# Specialized decorators
@cache_player_data(ttl=300)
@cache_match_data(ttl=120)
@cache_stats_data(ttl=600)
```

## Usage Examples

### User Management

```python
from database.repositories import UserRepository

user_repo = UserRepository()

# Create new user
user = await user_repo.create_user(
    user_id=123456789,
    faceit_player_id="player-uuid",
    faceit_nickname="PlayerName"
)

# Get user with subscription
user_with_sub = await user_repo.get_user_with_subscription(123456789)

# Update activity
await user_repo.update_last_activity(123456789)
```

### Subscription Management

```python
from database.repositories import SubscriptionRepository

sub_repo = SubscriptionRepository()

# Check rate limit
can_request, limits = await sub_repo.can_make_request(user.id)

# Upgrade subscription
subscription = await sub_repo.upgrade_subscription(
    user.id,
    SubscriptionTier.PREMIUM,
    duration_days=30
)

# Apply referral
success, error = await sub_repo.apply_referral(user.id, "REF123")
```

### Match Analysis

```python
from database.repositories import MatchRepository

match_repo = MatchRepository()

# Create analysis
analysis = await match_repo.create_analysis(
    user_id=user.id,
    match_id="match-123",
    analysis_data=analysis_results,
    processing_time_ms=15000
)

# Get user's analysis history
history = await match_repo.get_user_analyses(
    user.id,
    limit=20
)
```

### Player Statistics

```python
from database.repositories import StatsRepository

stats_repo = StatsRepository()

# Cache player stats
cached_stats = await stats_repo.cache_player_stats(
    player_id="player-uuid",
    nickname="PlayerName",
    stats_data=player_statistics,
    ttl_minutes=30
)

# Get team analysis
team_stats = await stats_repo.get_team_stats([
    "player1-uuid", "player2-uuid", "player3-uuid"
])
```

### Analytics

```python
from database.repositories import AnalyticsRepository

analytics_repo = AnalyticsRepository()

# Record metric
await analytics_repo.record_metric(
    "match_analysis_completed",
    value=1.0,
    tags={"user_tier": "premium"}
)

# Get dashboard data
dashboard = await analytics_repo.get_realtime_dashboard()
```

## Migration Strategy

### Phase 1: Repository Setup
1. Initialize database with models
2. Set up repository classes
3. Configure Redis connections
4. Test basic CRUD operations

### Phase 2: Data Migration
1. Export existing JSON data
2. Transform to repository format
3. Batch import with validation
4. Verify data integrity

### Phase 3: Application Integration
1. Update service layer to use repositories
2. Replace direct storage calls
3. Add caching layers
4. Performance testing

### Phase 4: Optimization
1. Monitor performance metrics
2. Optimize slow queries
3. Fine-tune cache TTLs
4. Add additional indexes

## Performance Considerations

### Database Optimization
- **Indexing**: Strategic indexes on frequently queried columns
- **Pagination**: Efficient offset/limit patterns
- **Batch Operations**: Bulk inserts/updates for better performance
- **Query Optimization**: Select only needed columns

### Cache Optimization
- **TTL Management**: Appropriate cache expiration times
- **Cache Invalidation**: Pattern-based cache clearing
- **Memory Usage**: Monitor Redis memory consumption
- **Hit Rate Monitoring**: Track cache effectiveness

### Connection Management
- **Connection Pooling**: Efficient database connection reuse
- **Async Operations**: Non-blocking database operations
- **Transaction Batching**: Group related operations
- **Error Recovery**: Robust error handling and retry logic

## Monitoring and Observability

### Metrics Collection
- Repository operation timing
- Cache hit/miss rates
- Database query performance
- Error rates and patterns

### Health Checks
- Database connectivity
- Redis availability
- Repository functionality
- Data consistency validation

### Logging
- Structured logging with correlation IDs
- Performance metrics logging
- Error tracking and alerting
- Usage pattern analysis

## Benefits

### Scalability
- Horizontal scaling with proper indexing
- Redis caching reduces database load
- Batch operations improve throughput
- Connection pooling optimizes resource usage

### Maintainability
- Clean separation of concerns
- Type-safe operations
- Comprehensive error handling
- Extensive test coverage support

### Performance
- Multi-level caching strategy
- Optimized query patterns
- Async operation support
- Efficient relationship loading

### Reliability
- Transaction management
- Automatic rollback on errors
- Data consistency validation
- Robust error recovery

This implementation provides a solid foundation for the FACEIT Bot's database layer, ensuring scalability, performance, and maintainability while preserving all existing functionality.