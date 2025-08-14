# Service Integration Guide

This guide provides comprehensive instructions for integrating the new PostgreSQL ORM Service layer with the existing JSON-based bot system.

## Overview

The integration provides:
- **Storage Abstraction**: Unified interface supporting both JSON and PostgreSQL
- **Migration Utilities**: Tools for migrating data between storage systems
- **Bot Integration**: Seamless service integration with automatic fallback
- **Configuration Management**: Runtime switching between storage types
- **Data Validation**: Consistency checks and fixing utilities

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Bot Handlers  │───▶│ BotIntegration   │───▶│ Storage Adapter │
└─────────────────┘    │    Adapter       │    └─────────────────┘
                       └──────────────────┘             │
                                │                       │
                       ┌─────────▼────────┐    ┌──────▼────────┐
                       │   Services       │    │ JSON Storage  │
                       │ - User Service   │    │              │
                       │ - Subscription   │    └───────────────┘
                       │ - Match Service  │             
                       │ - Analytics      │    ┌───────────────┐
                       └──────────────────┘    │ PostgreSQL    │
                                │              │   Services    │
                       ┌────────▼──────────┐   └───────────────┘
                       │   Repositories    │
                       │ - User Repo      │
                       │ - Subscription   │
                       │ - Match Repo     │
                       │ - Analytics      │
                       └───────────────────┘
```

## Quick Start

### 1. Configuration

Update your `.env` file with integration settings:

```bash
# Storage Backend Options: json, postgresql, dual
STORAGE_BACKEND=dual

# Migration Settings
MIGRATION_MODE=manual  # disabled, manual, auto
AUTO_MIGRATE=false
MIGRATION_BATCH_SIZE=50

# Service Integration
ENABLE_SERVICES=true
SERVICE_FALLBACK_ENABLED=true

# PostgreSQL Database
DATABASE_URL=postgresql://user:password@localhost:5432/faceit_bot
DB_ENVIRONMENT=production

# Feature Flags
ENABLE_MATCH_ANALYSIS=true
ENABLE_SUBSCRIPTION_SYSTEM=true
ENABLE_ANALYTICS=true
```

### 2. Initialize System

Replace your current `main.py` with the updated version:

```python
# Use main_updated.py instead of main.py
cp main_updated.py main.py
```

### 3. Update Bot Handlers

Replace your current bot handlers:

```python
# Use handlers_updated.py instead of handlers.py
cp bot/handlers_updated.py bot/handlers.py
```

### 4. Start the Bot

```bash
python main.py
```

The system will automatically:
- Initialize services if PostgreSQL is available
- Fall back to JSON storage if services fail
- Provide dual-mode operation during migration

## Storage Backend Options

### JSON Only (`json`)
- Uses existing JSON file storage
- No PostgreSQL dependencies
- Limited scalability
- Backward compatible

```bash
STORAGE_BACKEND=json
ENABLE_SERVICES=false
```

### PostgreSQL Only (`postgresql`)
- Uses PostgreSQL with ORM services
- Requires database setup
- Full scalability and features
- Best for production

```bash
STORAGE_BACKEND=postgresql
ENABLE_SERVICES=true
DATABASE_URL=postgresql://...
```

### Dual Mode (`dual`)
- Uses both storage systems
- Automatic migration support
- Zero-downtime transition
- Recommended for migration period

```bash
STORAGE_BACKEND=dual
ENABLE_SERVICES=true
MIGRATION_MODE=manual
```

## Migration Process

### Phase 1: Setup Dual Mode

1. Configure dual mode in `.env`:
```bash
STORAGE_BACKEND=dual
MIGRATION_MODE=manual
```

2. Start the bot - it will use both storage systems

3. Verify both systems are working:
```python
from adapters.storage_adapter import StorageAdapter
adapter = StorageAdapter()
health = await adapter.health_check()
print(health)
```

### Phase 2: Data Migration

#### Manual Migration

```python
from adapters.migration_adapter import MigrationAdapter
from adapters.storage_adapter import StorageAdapter

# Initialize migration adapter
migration_adapter = MigrationAdapter(...)

# Validate current state
integrity = await migration_adapter.validate_migration_integrity()
print(f"Integrity score: {integrity['integrity_score']}%")

# Migrate users
result = await migration_adapter.migrate_all_users(
    direction=MigrationDirection.JSON_TO_POSTGRESQL,
    batch_size=50,
    validation_mode=True
)

print(f"Migrated: {result.migrated_users}/{result.total_users} users")
```

#### Automatic Migration

```bash
# Enable auto-migration
AUTO_MIGRATE=true
MIGRATION_MODE=auto
```

The system will automatically migrate data on startup.

### Phase 3: Switch to PostgreSQL Only

After successful migration:

```bash
STORAGE_BACKEND=postgresql
MIGRATION_MODE=disabled
```

## Integration Components

### 1. Storage Adapter (`adapters/storage_adapter.py`)

Provides unified storage interface:

```python
from adapters.storage_adapter import StorageAdapter, StorageBackend

# Initialize adapter
adapter = StorageAdapter(
    backend=StorageBackend.DUAL,
    user_service=user_service,
    subscription_service=subscription_service
)

# Use unified interface
user = await adapter.get_user(user_id)
await adapter.save_user(user_data)
success = await adapter.can_make_request(user_id)
```

**Features:**
- Automatic backend detection
- Fallback support
- Health monitoring
- Performance tracking

### 2. Migration Adapter (`adapters/migration_adapter.py`)

Handles data migration between systems:

```python
from adapters.migration_adapter import MigrationAdapter

# Initialize migration
migration = MigrationAdapter(
    user_service=user_service,
    subscription_service=subscription_service,
    user_repository=user_repo,
    subscription_repository=subscription_repo
)

# Migrate all users
result = await migration.migrate_all_users()

# Migrate single user
user_result = await migration.migrate_single_user(user_id)

# Validate integrity
integrity = await migration.validate_migration_integrity()
```

**Features:**
- Batch processing
- Progress tracking
- Rollback support
- Data validation
- Error handling

### 3. Bot Integration Adapter (`adapters/bot_integration.py`)

Seamless service integration for bot handlers:

```python
from adapters.bot_integration import BotIntegrationAdapter

# Initialize integration
bot_adapter = BotIntegrationAdapter(
    storage_adapter=storage_adapter,
    user_service=user_service,
    subscription_service=subscription_service,
    match_service=match_service,
    analytics_service=analytics_service
)

# Use in handlers
user = await bot_adapter.get_or_create_user(user_id)
success, error = await bot_adapter.link_faceit_account(user_id, nickname)
can_request, reason = await bot_adapter.check_rate_limit(user_id)
```

**Features:**
- Automatic fallback
- Error handling
- Activity tracking
- Performance monitoring

### 4. Data Validation (`adapters/validation.py`)

Comprehensive data validation and fixing:

```python
from adapters.validation import DataValidator

# Initialize validator
validator = DataValidator(user_service, subscription_service)

# Validate all data
report = await validator.validate_all_data()

# Fix issues automatically
fix_summary = await validator.fix_validation_issues(
    report, 
    auto_fix=True,
    severity_threshold=ValidationSeverity.WARNING
)
```

**Features:**
- Data consistency checks
- Issue categorization
- Automatic fixing
- Comprehensive reporting

## Configuration Options

### Storage Settings

| Setting | Values | Description |
|---------|--------|-------------|
| `STORAGE_BACKEND` | `json`, `postgresql`, `dual` | Storage system to use |
| `MIGRATION_MODE` | `disabled`, `manual`, `auto` | Migration behavior |
| `AUTO_MIGRATE` | `true`, `false` | Automatic migration on startup |
| `MIGRATION_BATCH_SIZE` | `1-1000` | Users per migration batch |

### Service Settings

| Setting | Values | Description |
|---------|--------|-------------|
| `ENABLE_SERVICES` | `true`, `false` | Enable PostgreSQL services |
| `SERVICE_FALLBACK_ENABLED` | `true`, `false` | Enable JSON fallback |
| `HEALTH_CHECK_INTERVAL` | `60-3600` | Health check frequency (seconds) |

### Performance Settings

| Setting | Values | Description |
|---------|--------|-------------|
| `MAX_CONCURRENT_REQUESTS` | `1-1000` | Max concurrent operations |
| `REQUEST_TIMEOUT` | `10-300` | Request timeout (seconds) |
| `RETRY_ATTEMPTS` | `1-10` | Number of retry attempts |

### Feature Flags

| Setting | Values | Description |
|---------|--------|-------------|
| `ENABLE_MATCH_ANALYSIS` | `true`, `false` | Enable match analysis service |
| `ENABLE_SUBSCRIPTION_SYSTEM` | `true`, `false` | Enable subscription management |
| `ENABLE_REFERRAL_SYSTEM` | `true`, `false` | Enable referral system |
| `ENABLE_ANALYTICS` | `true`, `false` | Enable analytics tracking |

## Monitoring and Health Checks

### System Health

Check overall system health:

```python
# Via bot integration adapter
health = await bot_adapter.health_check()

# Direct storage health
storage_health = await storage_adapter.health_check()

# Service availability
service_info = bot_adapter.get_service_info()
```

### Performance Monitoring

Monitor key metrics:

```python
# Migration progress
migration_status = migration_adapter.get_migration_status(migration_id)

# Cache performance
cache_stats = await get_cache_stats()

# Database performance
db_health = await get_health_status()
```

### Logging

Configure logging for integration components:

```python
logging.getLogger('adapters').setLevel(logging.INFO)
logging.getLogger('services').setLevel(logging.INFO)
logging.getLogger('database.repositories').setLevel(logging.DEBUG)
```

## Troubleshooting

### Common Issues

#### 1. Services Not Available
```
⚠️ Services not available, using JSON fallback
```

**Solution:**
- Check PostgreSQL connection
- Verify `DATABASE_URL` configuration
- Ensure database is running and accessible

#### 2. Migration Failures
```
❌ Migration failed for user 123456789
```

**Solution:**
- Check data validation issues
- Run integrity check
- Migrate problematic users manually

#### 3. Storage Backend Mismatch
```
⚠️ PostgreSQL backend requires services to be enabled
```

**Solution:**
- Set `ENABLE_SERVICES=true`
- Or change to `STORAGE_BACKEND=json`

### Debug Mode

Enable debug mode for detailed logging:

```bash
LOG_LEVEL=DEBUG
DB_ECHO_SQL=true
```

### Manual Recovery

If automated systems fail:

1. **Backup Data:**
```python
# Export JSON data
import json
data = await json_storage.get_all_users()
with open('backup.json', 'w') as f:
    json.dump([user.dict() for user in data], f)
```

2. **Reset to JSON Mode:**
```bash
STORAGE_BACKEND=json
ENABLE_SERVICES=false
```

3. **Validate and Fix:**
```python
validator = DataValidator()
report = await validator.validate_all_data()
# Review and fix issues manually
```

## Best Practices

### 1. Migration Strategy

- **Start with dual mode** for safety
- **Migrate in small batches** (50-100 users)
- **Validate data integrity** before and after
- **Keep backups** of JSON data
- **Monitor performance** during migration

### 2. Configuration Management

- **Use environment files** for different deployments
- **Enable fallback** during transition period
- **Configure appropriate timeouts** based on load
- **Set up health monitoring** for production

### 3. Error Handling

- **Always check service results** for success/failure
- **Implement retry logic** for transient failures
- **Log errors appropriately** for debugging
- **Have rollback procedures** ready

### 4. Performance Optimization

- **Use appropriate batch sizes** for bulk operations
- **Enable caching** for frequently accessed data
- **Monitor database performance** and optimize queries
- **Consider connection pooling** for high load

## Development Workflow

### Local Development

1. **Setup dual mode** for testing both systems
2. **Use small datasets** for faster iteration
3. **Enable debug logging** for detailed information
4. **Test migration scenarios** thoroughly

### Testing

1. **Unit tests** for individual adapters
2. **Integration tests** for end-to-end scenarios
3. **Load testing** for performance validation
4. **Migration testing** with various data sets

### Production Deployment

1. **Backup current data** before migration
2. **Deploy in maintenance window** if possible
3. **Monitor system health** continuously
4. **Have rollback plan** ready

## Support and Maintenance

### Regular Tasks

- **Monitor migration progress** during transition
- **Check data integrity** periodically  
- **Update configuration** as needed
- **Review performance metrics** regularly

### Troubleshooting Resources

- **Health check endpoints** for system status
- **Validation reports** for data integrity
- **Migration status** for progress tracking
- **Detailed logging** for debugging

For additional support or questions about the integration, refer to the source code documentation in the `adapters/` directory.