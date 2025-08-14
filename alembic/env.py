"""
Alembic migration environment for FACEIT Telegram Bot.

This module provides async SQLAlchemy 2.0 support for database migrations
with automatic model discovery and environment variable integration.
"""

import asyncio
import logging
from logging.config import fileConfig
from typing import Optional

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

from alembic import context
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

# Add project root to path
import sys
import os
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import application components
from database.models import Base
try:
    from config.settings import settings
except ImportError:
    settings = None

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata

# Logger for migration operations
logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """
    Get database URL from environment variables or configuration.
    
    Returns:
        Database URL string
        
    Raises:
        ValueError: If no database URL is found
    """
    # Try to get from environment first
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        if settings:
            try:
                # Get from application settings directly
                from config.database import create_database_config_from_env
                db_config = create_database_config_from_env()
                database_url = db_config.database_url
            except Exception as e:
                logger.warning(f"Failed to get database configuration from settings: {e}")
        
        if not database_url:
            raise ValueError(
                "DATABASE_URL must be set as environment variable. Example: "
                "DATABASE_URL=postgresql+asyncpg://user:password@localhost/dbname"
            )
    
    # Ensure we use asyncpg driver for migrations
    if database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    elif not database_url.startswith('postgresql+asyncpg://'):
        raise ValueError("Database URL must use PostgreSQL with asyncpg driver")
    
    return database_url


def get_migration_context_config():
    """Get configuration for migration context."""
    return {
        # Include object names in diff
        'include_object': include_object,
        'include_name': include_name,
        
        # Compare types and other migration settings
        'compare_type': True,
        'compare_server_default': True,
        
        # Render options for better migration generation
        'render_as_batch': False,
        'render_item': render_item,
        
        # Transaction handling
        'transaction_per_migration': True,
    }


def include_object(object, name, type_, reflected, compare_to):
    """
    Filter objects to include in migrations.
    
    This function determines which database objects should be included
    in the migration generation process.
    """
    # Skip Alembic version table
    if type_ == "table" and name == "alembic_version":
        return False
    
    # Include all our application tables
    if type_ == "table" and name in target_metadata.tables:
        return True
    
    # Include indexes and constraints for our tables
    if hasattr(object, 'table') and object.table.name in target_metadata.tables:
        return True
    
    # Include all other objects by default
    return True


def include_name(name, type_, parent_names):
    """
    Filter names to include in migrations.
    
    This function provides additional filtering based on object names.
    """
    # Skip system schemas
    if type_ == "schema" and name in ("information_schema", "pg_catalog"):
        return False
    
    return True


def render_item(type_, obj, autogen_context):
    """
    Custom rendering for migration items.
    
    This allows for custom formatting of migration operations.
    """
    # Default rendering
    return False


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well. By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_database_url()
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **get_migration_context_config()
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations with a database connection.
    
    Args:
        connection: Database connection
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        **get_migration_context_config()
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in async mode.
    
    Creates an async engine and runs migrations in a sync context.
    """
    database_url = get_database_url()
    
    logger.info(f"Running async migrations with database URL: {database_url.split('@')[0]}@***")
    
    # Create async engine with migration-optimized settings
    connectable = create_async_engine(
        database_url,
        
        # Connection settings optimized for migrations
        poolclass=pool.NullPool,  # No pooling for migrations
        echo=os.getenv('ALEMBIC_ECHO_SQL', '').lower() == 'true',
        
        # Migration-specific connection args
        connect_args={
            "command_timeout": 300,  # 5 minutes for long migrations
            "server_settings": {
                "application_name": "faceit_bot_alembic",
                "lock_timeout": "300000",  # 5 minutes
            }
        }
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode using async engine.

    In this scenario we need to create an Engine and associate a connection
    with the context. We use async SQLAlchemy for this purpose.
    """
    try:
        asyncio.run(run_async_migrations())
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


# Determine migration mode and run
if context.is_offline_mode():
    logger.info("Running migrations in offline mode")
    run_migrations_offline()
else:
    logger.info("Running migrations in online mode")
    run_migrations_online()