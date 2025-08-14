# Database Migrations for FACEIT Telegram Bot

This directory contains Alembic migration setup and documentation for the FACEIT Telegram Bot PostgreSQL migration.

## Overview

The migration system uses **Alembic** with **SQLAlchemy 2.0** and **async support** to manage database schema changes for the transition from JSON-based storage to PostgreSQL.

## Migration Structure

```
migrations/
├── README.md                    # This file
├── alembic.ini                 # Alembic configuration
├── alembic/
│   ├── env.py                  # Migration environment with async support
│   ├── script.py.mako          # Migration script template
│   └── versions/               # Individual migration files
│       └── 20250814_1200_001_initial_migration.py
```

## Quick Start

### 1. Environment Setup

Ensure you have the required environment variables set:

```bash
# Required: PostgreSQL connection URL
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/faceit_bot

# Optional: Migration behavior
ALEMBIC_ECHO_SQL=true          # Show SQL commands during migration
DB_ENVIRONMENT=production       # Environment-specific settings
```

### 2. Initialize Migration Environment

The migration environment is already set up. To verify the setup:

```bash
# Check current migration status
alembic current

# Show migration history
alembic history --verbose
```

### 3. Apply Migrations

```bash
# Upgrade to latest migration (recommended)
alembic upgrade head

# Upgrade to specific revision
alembic upgrade 001

# Show SQL without executing (dry run)
alembic upgrade head --sql
```

### 4. Rollback Migrations

```bash
# Downgrade by one revision
alembic downgrade -1

# Downgrade to specific revision
alembic downgrade 001

# Downgrade to base (removes all tables)
alembic downgrade base
```

## Migration Commands

### Generate New Migrations

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Add new feature"

# Create empty migration file
alembic revision -m "Custom changes"
```

### Migration Information

```bash
# Show current revision
alembic current

# Show all revisions
alembic history

# Show specific revision details
alembic show 001
```

### Database Operations

```bash
# Create database tables from scratch (alternative to migrations)
python -c "
import asyncio
from database.connection import init_database
from config.settings import settings

async def create_tables():
    db_config = settings.get_database_config()
    db_manager = await init_database(db_config)
    await db_manager.create_tables(drop_existing=False)
    await db_manager.close()

asyncio.run(create_tables())
"
```

## Migration Files

### Initial Migration (001)

- **File**: `20250814_1200_001_initial_migration.py`
- **Purpose**: Creates all base tables for the bot
- **Tables Created**:
  - `users` - User accounts and FACEIT integration
  - `user_subscriptions` - Subscription tiers and limits
  - `match_analyses` - Match analysis history
  - `player_stats_cache` - Cached player statistics
  - `payments` - Payment history and Telegram Stars
  - `match_cache` - Cached match data
  - `system_settings` - Bot configuration
  - `analytics` - Usage metrics and analytics

### Database Schema Features

- **UUID Primary Keys**: All tables use UUID primary keys for better scalability
- **Automatic Timestamps**: `created_at` and `updated_at` columns with triggers
- **Enums**: Type-safe enums for subscription tiers, payment status, match status
- **JSON Columns**: Flexible storage for complex data structures
- **Indexes**: Optimized indexes for common query patterns
- **Foreign Keys**: Proper relationships with cascade delete
- **Constraints**: Data integrity constraints and validations

## Environment-Specific Settings

The migration system adapts to different environments:

### Development
- SQL echoing enabled
- Smaller connection pool
- Detailed logging
- No backups

### Testing
- No connection pooling
- Single connection
- Minimal logging
- Fast execution

### Production
- Optimized connection pool
- Slow query logging
- Backup integration
- Performance monitoring

## Data Migration

### From JSON to PostgreSQL

The migration includes helper utilities in `database/models.py`:

```python
from database.models import MigrationHelper

# Convert JSON user data to PostgreSQL format
json_data = {"user_id": 123456, "faceit_nickname": "player"}
user_data = MigrationHelper.convert_user_data_from_json(json_data)
subscription_data = MigrationHelper.convert_subscription_from_json(json_data)
```

### Migration Script Template

```python
# Example data migration
def upgrade():
    # Schema changes
    op.add_column('users', sa.Column('new_field', sa.String(50)))
    
    # Data migration
    connection = op.get_bind()
    connection.execute("UPDATE users SET new_field = 'default_value'")

def downgrade():
    op.drop_column('users', 'new_field')
```

## Troubleshooting

### Common Issues

1. **Connection Errors**
   ```bash
   # Check database connectivity
   python -c "
   import asyncio
   from database.connection import check_database_exists
   from config.settings import settings
   
   db_config = settings.get_database_config()
   exists = asyncio.run(check_database_exists(db_config.database_url))
   print(f'Database exists: {exists}')
   "
   ```

2. **Migration Conflicts**
   ```bash
   # Show current migration state
   alembic current
   
   # Manually set migration head (if needed)
   alembic stamp head
   ```

3. **Schema Validation**
   ```bash
   # Validate migration without applying
   alembic upgrade head --sql > migration.sql
   # Review migration.sql before applying
   ```

### Recovery Procedures

1. **Backup Before Migration**
   ```bash
   pg_dump $DATABASE_URL > backup_before_migration.sql
   ```

2. **Rollback on Failure**
   ```bash
   # If migration fails, rollback
   alembic downgrade -1
   
   # Restore from backup if needed
   psql $DATABASE_URL < backup_before_migration.sql
   ```

## Integration with Bot

The migration system is integrated with the bot's configuration:

```python
# In main.py or initialization code
from database.connection import init_database
from config.settings import settings

async def init_app():
    # Initialize database
    db_config = settings.get_database_config()
    db_manager = await init_database(db_config)
    
    # Run migrations automatically (optional)
    if db_config.enable_migrations:
        import subprocess
        subprocess.run(["alembic", "upgrade", "head"], check=True)
```

## Performance Considerations

- **Migration Duration**: Initial migration creates ~8 tables with indexes
- **Downtime**: Estimated 30-60 seconds for initial migration
- **Resource Usage**: Uses single connection during migration
- **Rollback Time**: Downgrade operations are typically faster

## Security Notes

- Database credentials are loaded from environment variables
- Migration logs may contain sensitive information in development
- Production migrations should be run with restricted database user
- Always backup before running migrations in production

## Support

For issues with migrations:

1. Check the migration logs: `alembic.log`
2. Validate environment variables: `DATABASE_URL`, `DB_ENVIRONMENT`
3. Test connection manually using database tools
4. Review migration file for conflicts
5. Use dry-run mode to preview changes: `--sql` flag