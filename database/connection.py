"""
Async database connection manager for PostgreSQL using SQLAlchemy 2.0.

This module provides:
- Async database engine and session management
- Connection pooling with proper configuration
- Error handling and retry logic
- Health check functionality
- Migration support preparation
- Integration with existing Redis cache
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Dict, Any, Callable
from datetime import datetime, timedelta

import asyncpg
from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import (
    create_async_engine, 
    AsyncEngine, 
    AsyncSession, 
    async_sessionmaker,
    async_scoped_session
)
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import SQLAlchemyError, DisconnectionError
from asyncpg.exceptions import PostgresError

from database.models import Base
from config.database import DatabaseConfig

logger = logging.getLogger(__name__)


class DatabaseConnectionManager:
    """
    Async database connection manager with connection pooling,
    error handling, retry logic, and health checks.
    """
    
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None
        self.scoped_session: Optional[async_scoped_session[AsyncSession]] = None
        self._connected = False
        self._connection_attempts = 0
        self._last_health_check: Optional[datetime] = None
        self._health_check_failed_count = 0
    
    async def initialize(self) -> None:
        """
        Initialize the database engine and session factory.
        
        Raises:
            DatabaseConnectionError: If connection fails after all retries
        """
        logger.info("🔄 Initializing PostgreSQL database connection...")
        logger.info(f"Database URL: {self.config.database_url.split('@')[0] if '@' in self.config.database_url else 'No credentials'}@***")
        logger.info(f"Pool enabled: {self.config.enable_connection_pooling}, Pool size: {self.config.pool_size}")
        
        for attempt in range(self.config.max_retries):
            try:
                # Create async engine with simplified configuration
                engine_kwargs = {
                    "echo": self.config.echo_sql,
                    "connect_args": {
                        "command_timeout": self.config.command_timeout,
                        "server_settings": {
                            "application_name": f"faceit_bot_{self.config.environment}",
                        }
                    }
                }
                
                # Add pooling configuration if enabled
                if self.config.enable_connection_pooling:
                    engine_kwargs.update({
                        "pool_size": self.config.pool_size,
                        "max_overflow": self.config.pool_overflow,
                        "pool_timeout": self.config.pool_timeout,
                        "pool_recycle": self.config.pool_recycle,
                    })
                else:
                    engine_kwargs["poolclass"] = NullPool
                
                self.engine = create_async_engine(
                    self.config.database_url,
                    **engine_kwargs
                )
                
                # Add event listeners
                self._setup_engine_events()
                
                # Test connection
                async with self.engine.begin() as conn:
                    result = await conn.execute(text("SELECT 1"))
                    result.fetchone()
                
                # Create session factory
                self.session_factory = async_sessionmaker(
                    bind=self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                    autoflush=True,
                    autocommit=False
                )
                
                # Create scoped session for thread-local session management
                self.scoped_session = async_scoped_session(
                    self.session_factory,
                    scopefunc=asyncio.current_task
                )
                
                self._connected = True
                self._connection_attempts = attempt + 1
                self._last_health_check = datetime.now()
                
                logger.info(f"✅ PostgreSQL connected successfully on attempt {attempt + 1}")
                if self.config.enable_connection_pooling:
                    logger.info(f"📊 Pool size: {self.config.pool_size}, Max overflow: {self.config.pool_overflow}")
                else:
                    logger.info("📊 Using NullPool (no connection pooling)")
                return
                
            except (PostgresError, SQLAlchemyError, Exception) as e:
                self._connection_attempts = attempt + 1
                logger.warning(
                    f"Database connection attempt {attempt + 1}/{self.config.max_retries} failed: {e}"
                )
                
                if attempt < self.config.max_retries - 1:
                    wait_time = min(self.config.retry_interval * (2 ** attempt), 30)
                    logger.info(f"⏳ Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    error_msg = f"❌ Failed to connect to database after {self.config.max_retries} attempts"
                    logger.error(error_msg)
                    raise DatabaseConnectionError(error_msg) from e
    
    def _setup_engine_events(self) -> None:
        """Setup SQLAlchemy engine event listeners for monitoring and debugging."""
        if not self.engine:
            return
        
        @event.listens_for(self.engine.sync_engine, "connect")
        def on_connect(dbapi_connection, connection_record):
            """Event listener for new database connections."""
            logger.debug("🔗 New database connection established")
        
        @event.listens_for(self.engine.sync_engine, "checkout")
        def on_checkout(dbapi_connection, connection_record, connection_proxy):
            """Event listener for connection checkout from pool."""
            logger.debug("📤 Database connection checked out from pool")
        
        @event.listens_for(self.engine.sync_engine, "checkin")
        def on_checkin(dbapi_connection, connection_record):
            """Event listener for connection checkin to pool."""
            logger.debug("📥 Database connection checked back into pool")
        
        @event.listens_for(self.engine.sync_engine, "close")
        def on_close(dbapi_connection, connection_record):
            """Event listener for connection close."""
            logger.debug("❌ Database connection closed")
        
        if self.config.log_slow_queries:
            @event.listens_for(self.engine.sync_engine, "before_cursor_execute")
            def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                context._query_start_time = datetime.now()
            
            @event.listens_for(self.engine.sync_engine, "after_cursor_execute")
            def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
                total = (datetime.now() - context._query_start_time).total_seconds()
                if total > self.config.slow_query_threshold:
                    logger.warning(f"🐌 Slow query ({total:.3f}s): {statement[:200]}...")
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session with automatic transaction handling.
        
        Usage:
            async with db_manager.get_session() as session:
                # Use session here
                result = await session.execute(...)
                await session.commit()
        
        Yields:
            AsyncSession: Database session
        """
        if not self._connected or not self.session_factory:
            raise DatabaseConnectionError("Database not connected")
        
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error, rolled back: {e}")
            raise
        finally:
            await session.close()
    
    @asynccontextmanager
    async def get_scoped_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a scoped async database session (task-local).
        
        Yields:
            AsyncSession: Scoped database session
        """
        if not self._connected or not self.scoped_session:
            raise DatabaseConnectionError("Database not connected")
        
        session = self.scoped_session()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Scoped database session error, rolled back: {e}")
            raise
        finally:
            await self.scoped_session.remove()
    
    async def execute_raw_query(
        self, 
        query: str, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Execute a raw SQL query.
        
        Args:
            query: SQL query string
            parameters: Query parameters
            
        Returns:
            Query result
        """
        async with self.get_session() as session:
            result = await session.execute(text(query), parameters or {})
            return result
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive database health check.
        
        Returns:
            Dict with health check results
        """
        health_info = {
            "connected": self._connected,
            "last_check": self._last_health_check.isoformat() if self._last_health_check else None,
            "connection_attempts": self._connection_attempts,
            "failed_checks": self._health_check_failed_count,
        }
        
        if not self._connected or not self.engine:
            health_info["status"] = "disconnected"
            return health_info
        
        try:
            start_time = datetime.now()
            
            # Test basic connectivity
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            
            # Get connection pool info if available
            if hasattr(self.engine.pool, 'size'):
                pool_info = {
                    "pool_size": self.engine.pool.size(),
                    "checked_in": self.engine.pool.checkedin(),
                    "checked_out": self.engine.pool.checkedout(),
                    "overflow": getattr(self.engine.pool, 'overflow', lambda: -1)(),
                }
                health_info["pool"] = pool_info
            
            # Get database version and basic stats
            async with self.get_session() as session:
                # PostgreSQL version
                version_result = await session.execute(text("SELECT version()"))
                version = version_result.scalar()
                health_info["database_version"] = version.split()[1] if version else "unknown"
                
                # Connection count
                conn_result = await session.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
                )
                health_info["active_connections"] = conn_result.scalar()
                
                # Database size
                size_result = await session.execute(
                    text("SELECT pg_size_pretty(pg_database_size(current_database()))")
                )
                health_info["database_size"] = size_result.scalar()
            
            response_time = (datetime.now() - start_time).total_seconds()
            health_info.update({
                "status": "healthy",
                "response_time": f"{response_time:.3f}s",
                "last_check": datetime.now().isoformat()
            })
            
            self._last_health_check = datetime.now()
            self._health_check_failed_count = 0
            
        except Exception as e:
            self._health_check_failed_count += 1
            health_info.update({
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.now().isoformat()
            })
            logger.error(f"Database health check failed: {e}")
        
        return health_info
    
    async def create_tables(self, drop_existing: bool = False) -> None:
        """
        Create all database tables.
        
        Args:
            drop_existing: Whether to drop existing tables first
        """
        if not self.engine:
            raise DatabaseConnectionError("Database not connected")
        
        try:
            async with self.engine.begin() as conn:
                if drop_existing:
                    logger.warning("🗑️ Dropping existing tables...")
                    await conn.run_sync(Base.metadata.drop_all)
                
                logger.info("🏗️ Creating database tables...")
                await conn.run_sync(Base.metadata.create_all)
                
            logger.info("✅ Database tables created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise DatabaseOperationError(f"Table creation failed: {e}") from e
    
    async def close(self) -> None:
        """Close database connections and cleanup resources."""
        if self.engine:
            logger.info("🔄 Closing database connections...")
            
            # Remove scoped sessions
            if self.scoped_session:
                await self.scoped_session.remove()
            
            # Close engine
            await self.engine.dispose()
            
            self._connected = False
            logger.info("✅ Database connections closed")
    
    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._connected and self.engine is not None
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """Get current connection statistics."""
        stats = {
            "connected": self._connected,
            "connection_attempts": self._connection_attempts,
            "last_health_check": self._last_health_check.isoformat() if self._last_health_check else None,
            "health_check_failures": self._health_check_failed_count,
        }
        
        if self.engine and hasattr(self.engine.pool, 'size'):
            stats["pool"] = {
                "size": self.engine.pool.size(),
                "checked_in": self.engine.pool.checkedin(),
                "checked_out": self.engine.pool.checkedout(),
            }
        
        return stats


class DatabaseOperationError(Exception):
    """Raised when a database operation fails."""
    pass


class DatabaseConnectionError(Exception):
    """Raised when database connection fails."""
    pass


# Global database manager instance
db_manager: Optional[DatabaseConnectionManager] = None


async def init_database(config: DatabaseConfig) -> DatabaseConnectionManager:
    """
    Initialize global database manager.
    
    Args:
        config: Database configuration
        
    Returns:
        DatabaseConnectionManager instance
    """
    global db_manager
    
    db_manager = DatabaseConnectionManager(config)
    await db_manager.initialize()
    
    return db_manager


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session using the global database manager.
    
    Usage:
        async with get_db_session() as session:
            # Use session here
    
    Yields:
        AsyncSession: Database session
    """
    if not db_manager:
        raise DatabaseConnectionError("Database not initialized")
    
    async with db_manager.get_session() as session:
        yield session


async def get_db_scoped_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a scoped database session using the global database manager.
    
    Yields:
        AsyncSession: Scoped database session
    """
    if not db_manager:
        raise DatabaseConnectionError("Database not initialized")
    
    async with db_manager.get_scoped_session() as session:
        yield session


async def close_database() -> None:
    """Close the global database manager."""
    global db_manager
    
    if db_manager:
        await db_manager.close()
        db_manager = None


# Dependency injection function for FastAPI-style usage
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection function for database sessions."""
    async with get_db_session() as session:
        yield session


# Utility functions for migration support
async def check_database_exists(database_url: str) -> bool:
    """
    Check if database exists.
    
    Args:
        database_url: Database URL
        
    Returns:
        True if database exists, False otherwise
    """
    try:
        # Parse database URL to get database name
        import re
        match = re.search(r'/([^/?]+)(?:\?|$)', database_url)
        if not match:
            return False
        
        db_name = match.group(1)
        
        # Connect to postgres database to check if target exists
        base_url = database_url.replace(f'/{db_name}', '/postgres')
        
        engine = create_async_engine(base_url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :db_name"),
                    {"db_name": db_name}
                )
                exists = await result.fetchone() is not None
            
            return exists
        finally:
            await engine.dispose()
            
    except Exception as e:
        logger.error(f"Error checking database existence: {e}")
        return False


async def create_database_if_not_exists(database_url: str) -> bool:
    """
    Create database if it doesn't exist.
    
    Args:
        database_url: Database URL
        
    Returns:
        True if database was created or already exists, False on failure
    """
    try:
        if await check_database_exists(database_url):
            return True
        
        # Parse database URL to get database name
        import re
        match = re.search(r'/([^/?]+)(?:\?|$)', database_url)
        if not match:
            logger.error("Could not parse database name from URL")
            return False
        
        db_name = match.group(1)
        
        # Connect to postgres database to create target
        base_url = database_url.replace(f'/{db_name}', '/postgres')
        
        engine = create_async_engine(base_url)
        try:
            async with engine.begin() as conn:
                # Use autocommit for CREATE DATABASE
                await conn.execute(text("COMMIT"))
                await conn.execute(text(f"CREATE DATABASE {db_name}"))
            
            logger.info(f"✅ Database '{db_name}' created successfully")
            return True
            
        finally:
            await engine.dispose()
            
    except Exception as e:
        logger.error(f"Error creating database: {e}")
        return False


# Context manager for database transactions
@asynccontextmanager
async def db_transaction() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database transactions with automatic rollback on errors.
    
    Usage:
        async with db_transaction() as session:
            # All operations in this block are in a single transaction
            await session.execute(...)
    """
    async with get_db_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise