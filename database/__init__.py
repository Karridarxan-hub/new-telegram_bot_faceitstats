"""
Database package for FACEIT Telegram Bot.

This package provides:
- SQLAlchemy 2.0 async models and database schema
- Database connection management with pooling
- Migration utilities for JSON to PostgreSQL transition
- Health checks and monitoring
- Integration with existing Redis cache system

Usage:
    from database import init_database, get_db_session, db_manager
    from database.models import User, UserSubscription, MatchAnalysis
    from config.database import get_database_config
    
    # Initialize database
    config = get_database_config()
    await init_database(config)
    
    # Use database session
    async with get_db_session() as session:
        user = await session.get(User, user_id)
"""

from database.connection import (
    # Main database manager
    DatabaseConnectionManager,
    db_manager,
    
    # Connection functions
    init_database,
    close_database,
    
    # Session management
    get_db_session,
    get_db_scoped_session,
    get_db,
    db_transaction,
    
    # Utility functions
    check_database_exists,
    create_database_if_not_exists,
    
    # Exceptions
    DatabaseConnectionError,
    DatabaseOperationError,
)

from database.models import (
    # Base model
    Base,
    
    # Enums
    SubscriptionTier,
    MatchStatus,
    PaymentStatus,
    
    # Core models
    User,
    UserSubscription,
    MatchAnalysis,
    PlayerStatsCache,
    Payment,
    MatchCache,
    SystemSettings,
    Analytics,
    
    # Migration helper
    MigrationHelper,
)

# Package metadata
__version__ = "1.0.0"
__author__ = "FACEIT Bot Team"
__description__ = "PostgreSQL database integration for FACEIT Telegram Bot"

# Export key components for easy access
__all__ = [
    # Connection management
    "DatabaseConnectionManager",
    "db_manager",
    "init_database",
    "close_database",
    
    # Session management
    "get_db_session",
    "get_db_scoped_session", 
    "get_db",
    "db_transaction",
    
    # Models
    "Base",
    "User",
    "UserSubscription",
    "MatchAnalysis",
    "PlayerStatsCache",
    "Payment",
    "MatchCache",
    "SystemSettings",
    "Analytics",
    
    # Enums
    "SubscriptionTier",
    "MatchStatus", 
    "PaymentStatus",
    
    # Utilities
    "check_database_exists",
    "create_database_if_not_exists",
    "MigrationHelper",
    
    # Exceptions
    "DatabaseConnectionError",
    "DatabaseOperationError",
]

# Package-level convenience functions
async def get_health_status():
    """Get database health status."""
    if db_manager:
        return await db_manager.health_check()
    return {"connected": False, "error": "Database not initialized"}


async def get_connection_stats():
    """Get database connection statistics."""
    if db_manager:
        return db_manager.get_connection_stats()
    return {"connected": False, "error": "Database not initialized"}


def is_database_connected():
    """Check if database is connected."""
    return db_manager and db_manager.is_connected


# Development utilities
async def reset_database():
    """Reset database (DROP and CREATE all tables) - USE WITH CAUTION!"""
    if not db_manager:
        raise DatabaseConnectionError("Database not initialized")
    
    import logging
    logger = logging.getLogger(__name__)
    
    logger.warning("🚨 RESETTING DATABASE - ALL DATA WILL BE LOST!")
    await db_manager.create_tables(drop_existing=True)
    logger.info("✅ Database reset completed")


# Migration utilities
async def migrate_from_json(json_file_path: str, batch_size: int = 100):
    """
    Migrate data from JSON storage to PostgreSQL.
    
    Args:
        json_file_path: Path to JSON data file
        batch_size: Number of records to process in each batch
    """
    if not db_manager:
        raise DatabaseConnectionError("Database not initialized")
    
    import json
    import logging
    from datetime import datetime
    
    logger = logging.getLogger(__name__)
    
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        logger.info(f"🔄 Starting migration from {json_file_path}")
        logger.info(f"📊 Found {len(json_data)} records to migrate")
        
        migrated_count = 0
        async with get_db_session() as session:
            for user_id, user_data in json_data.items():
                try:
                    # Convert user data
                    user_dict = MigrationHelper.convert_user_data_from_json(user_data)
                    user = User(**user_dict)
                    session.add(user)
                    
                    # Convert subscription data
                    if 'subscription' in user_data:
                        sub_dict = MigrationHelper.convert_subscription_from_json(user_data)
                        sub_dict['user_id'] = user.id
                        subscription = UserSubscription(**sub_dict)
                        session.add(subscription)
                    
                    migrated_count += 1
                    
                    # Commit in batches
                    if migrated_count % batch_size == 0:
                        await session.commit()
                        logger.info(f"📦 Migrated {migrated_count} records...")
                
                except Exception as e:
                    logger.error(f"Error migrating user {user_id}: {e}")
                    await session.rollback()
                    continue
            
            # Final commit
            await session.commit()
        
        logger.info(f"✅ Migration completed: {migrated_count} records migrated")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


# Package initialization check
def _validate_package_dependencies():
    """Validate that required dependencies are installed."""
    try:
        import sqlalchemy
        import asyncpg
        import alembic
        
        # Check SQLAlchemy version
        from packaging import version
        if version.parse(sqlalchemy.__version__) < version.parse("2.0.0"):
            raise ImportError("SQLAlchemy 2.0+ is required")
            
    except ImportError as e:
        raise ImportError(
            f"Missing required database dependencies: {e}\n"
            "Please install: pip install sqlalchemy[asyncio] asyncpg alembic"
        )


# Validate dependencies on import
try:
    _validate_package_dependencies()
except ImportError as e:
    import warnings
    warnings.warn(f"Database package warning: {e}", ImportWarning)