#!/usr/bin/env python3
"""
Production Database Configuration for Supabase PostgreSQL.

This module provides optimized database configuration for production deployment
with Supabase, including connection pooling, retry logic, failover mechanisms,
and Docker-compatible settings.

Features:
- Multiple connection endpoint support (pooler + direct)
- Intelligent failover and retry logic
- Docker network compatibility
- Connection pool optimization
- Performance monitoring
- Health check mechanisms
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Tuple, AsyncGenerator
from dataclasses import dataclass
from enum import Enum

import asyncpg
from asyncpg.pool import Pool

logger = logging.getLogger(__name__)


class ConnectionType(Enum):
    """Database connection types."""
    POOLER = "pooler"
    DIRECT = "direct"


@dataclass
class DatabaseEndpoint:
    """Database endpoint configuration."""
    name: str
    connection_type: ConnectionType
    host: str
    port: int
    database: str
    username: str
    password: str
    priority: int = 1  # Lower number = higher priority
    
    def get_url(self) -> str:
        """Get connection URL."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    def get_asyncpg_url(self) -> str:
        """Get asyncpg compatible URL."""
        return self.get_url()
    
    def get_sqlalchemy_url(self) -> str:
        """Get SQLAlchemy compatible URL."""
        return f"postgresql+asyncpg://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


class ProductionDatabaseManager:
    """
    Production-ready database manager with failover, pooling, and monitoring.
    
    Features:
    - Multiple endpoint support with automatic failover
    - Connection pooling with health checks
    - Retry logic with exponential backoff
    - Performance monitoring and metrics
    - Docker network compatibility
    """
    
    def __init__(self, endpoints: List[DatabaseEndpoint], config: Optional[Dict] = None):
        self.endpoints = sorted(endpoints, key=lambda x: x.priority)
        self.config = config or self._get_default_config()
        self.pools: Dict[str, Pool] = {}
        self.active_endpoint: Optional[DatabaseEndpoint] = None
        self.connection_stats = {
            'total_connections': 0,
            'failed_connections': 0,
            'successful_connections': 0,
            'failover_count': 0,
            'last_failover': None,
            'endpoint_stats': {}
        }
        self._initialized = False
    
    def _get_default_config(self) -> Dict:
        """Get default production configuration."""
        return {
            # Connection pool settings
            'min_pool_size': int(os.getenv('DB_MIN_POOL_SIZE', '5')),
            'max_pool_size': int(os.getenv('DB_MAX_POOL_SIZE', '20')),
            'pool_setup_timeout': int(os.getenv('DB_POOL_SETUP_TIMEOUT', '60')),
            'pool_connection_timeout': int(os.getenv('DB_CONNECTION_TIMEOUT', '15')),
            
            # Retry settings
            'max_retry_attempts': int(os.getenv('DB_MAX_RETRIES', '5')),
            'retry_base_delay': float(os.getenv('DB_RETRY_BASE_DELAY', '1.0')),
            'retry_max_delay': float(os.getenv('DB_RETRY_MAX_DELAY', '30.0')),
            
            # Health check settings
            'health_check_interval': int(os.getenv('DB_HEALTH_CHECK_INTERVAL', '60')),
            'health_check_timeout': int(os.getenv('DB_HEALTH_CHECK_TIMEOUT', '10')),
            'max_failed_health_checks': int(os.getenv('DB_MAX_FAILED_HEALTH_CHECKS', '3')),
            
            # Connection settings
            'command_timeout': int(os.getenv('DB_COMMAND_TIMEOUT', '60')),
            'connection_max_age': int(os.getenv('DB_CONNECTION_MAX_AGE', '3600')),
            
            # Failover settings
            'failover_retry_delay': float(os.getenv('DB_FAILOVER_RETRY_DELAY', '5.0')),
            'failover_timeout': int(os.getenv('DB_FAILOVER_TIMEOUT', '30')),
            
            # Monitoring
            'enable_monitoring': os.getenv('DB_ENABLE_MONITORING', 'true').lower() == 'true',
            'log_slow_queries': os.getenv('DB_LOG_SLOW_QUERIES', 'true').lower() == 'true',
            'slow_query_threshold': float(os.getenv('DB_SLOW_QUERY_THRESHOLD', '1.0')),
        }
    
    async def initialize(self) -> None:
        """Initialize database connections with failover support."""
        logger.info("🚀 Initializing production database manager...")
        logger.info(f"📊 Endpoints configured: {len(self.endpoints)}")
        
        for endpoint in self.endpoints:
            logger.info(f"   • {endpoint.name} ({endpoint.connection_type.value}): {endpoint.host}:{endpoint.port}")
        
        # Try to connect to endpoints in priority order
        for endpoint in self.endpoints:
            try:
                logger.info(f"🔄 Attempting connection to {endpoint.name}...")
                pool = await self._create_pool(endpoint)
                
                # Test the pool with a simple query
                async with pool.acquire() as conn:
                    await conn.fetchval('SELECT 1')
                
                self.pools[endpoint.name] = pool
                self.active_endpoint = endpoint
                self.connection_stats['successful_connections'] += 1
                
                logger.info(f"✅ Connected to {endpoint.name} successfully")
                logger.info(f"📊 Pool: {pool.get_size()} connections ({pool.get_idle_size()} idle)")
                break
                
            except Exception as e:
                logger.warning(f"⚠️ Failed to connect to {endpoint.name}: {e}")
                self.connection_stats['failed_connections'] += 1
                self.connection_stats['endpoint_stats'][endpoint.name] = {
                    'last_error': str(e),
                    'last_attempt': time.time()
                }
                continue
        
        if not self.active_endpoint:
            raise ConnectionError("❌ Failed to connect to any database endpoint")
        
        self._initialized = True
        logger.info(f"✅ Database manager initialized with {self.active_endpoint.name}")
        
        # Start background health checks if enabled
        if self.config['enable_monitoring']:
            asyncio.create_task(self._health_check_loop())
    
    async def _create_pool(self, endpoint: DatabaseEndpoint) -> Pool:
        """Create connection pool for an endpoint."""
        pool_kwargs = {
            'dsn': endpoint.get_asyncpg_url(),
            'min_size': self.config['min_pool_size'],
            'max_size': self.config['max_pool_size'],
            'setup': self._setup_connection,
            'init': self._init_connection,
            'command_timeout': self.config['command_timeout'],
            'max_cached_statement_lifetime': self.config['connection_max_age'],
            'max_cacheable_statement_size': 1024 * 16,  # 16KB
        }
        
        # Create pool with timeout
        pool = await asyncio.wait_for(
            asyncpg.create_pool(**pool_kwargs),
            timeout=self.config['pool_setup_timeout']
        )
        
        return pool
    
    async def _setup_connection(self, conn: asyncpg.Connection) -> None:
        """Setup function called for each new connection."""
        # Set connection parameters for optimal performance
        await conn.execute("SET application_name = 'faceit_bot_production'")
        await conn.execute("SET timezone = 'UTC'")
        await conn.execute("SET statement_timeout = '60s'")
        await conn.execute("SET lock_timeout = '30s'")
        await conn.execute("SET idle_in_transaction_session_timeout = '300s'")
        
        # Disable JIT for faster connection setup
        await conn.execute("SET jit = off")
        
        logger.debug("🔧 Database connection configured")
    
    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize function called for each connection."""
        # Add any custom types or extensions here if needed
        pass
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """
        Get a database connection with automatic failover.
        
        Usage:
            async with db_manager.get_connection() as conn:
                result = await conn.fetchval("SELECT 1")
        """
        if not self._initialized:
            raise RuntimeError("Database manager not initialized")
        
        connection = None
        last_error = None
        
        # Try current active endpoint first
        if self.active_endpoint and self.active_endpoint.name in self.pools:
            try:
                pool = self.pools[self.active_endpoint.name]
                connection = await asyncio.wait_for(
                    pool.acquire(),
                    timeout=self.config['pool_connection_timeout']
                )
                
                # Test connection with a simple query
                await asyncio.wait_for(
                    connection.fetchval('SELECT 1'),
                    timeout=5.0
                )
                
            except Exception as e:
                last_error = e
                logger.warning(f"⚠️ Connection failed on {self.active_endpoint.name}: {e}")
                
                if connection:
                    try:
                        await self.pools[self.active_endpoint.name].release(connection)
                    except:
                        pass
                    connection = None
                
                # Attempt failover
                await self._attempt_failover()
        
        # If primary failed, try failover endpoints
        if not connection:
            for endpoint in self.endpoints:
                if endpoint.name == self.active_endpoint.name:
                    continue  # Skip current active (already tried)
                
                try:
                    if endpoint.name not in self.pools:
                        logger.info(f"🔄 Creating pool for failover endpoint {endpoint.name}")
                        self.pools[endpoint.name] = await self._create_pool(endpoint)
                    
                    pool = self.pools[endpoint.name]
                    connection = await asyncio.wait_for(
                        pool.acquire(),
                        timeout=self.config['pool_connection_timeout']
                    )
                    
                    # Test connection
                    await asyncio.wait_for(
                        connection.fetchval('SELECT 1'),
                        timeout=5.0
                    )
                    
                    # Update active endpoint
                    old_endpoint = self.active_endpoint.name if self.active_endpoint else "None"
                    self.active_endpoint = endpoint
                    self.connection_stats['failover_count'] += 1
                    self.connection_stats['last_failover'] = time.time()
                    
                    logger.warning(f"🔄 Failover: {old_endpoint} → {endpoint.name}")
                    break
                    
                except Exception as e:
                    last_error = e
                    logger.warning(f"⚠️ Failover to {endpoint.name} failed: {e}")
                    if connection:
                        try:
                            await self.pools[endpoint.name].release(connection)
                        except:
                            pass
                        connection = None
                    continue
        
        if not connection:
            raise ConnectionError(f"Failed to acquire database connection. Last error: {last_error}")
        
        try:
            self.connection_stats['total_connections'] += 1
            yield connection
        finally:
            if connection and self.active_endpoint:
                try:
                    await self.pools[self.active_endpoint.name].release(connection)
                except Exception as e:
                    logger.error(f"Error releasing connection: {e}")
    
    async def _attempt_failover(self) -> None:
        """Attempt to failover to a different endpoint."""
        if not self.active_endpoint:
            return
        
        logger.warning(f"🔄 Attempting failover from {self.active_endpoint.name}")
        
        # Close current pool if it's having issues
        try:
            if self.active_endpoint.name in self.pools:
                await self.pools[self.active_endpoint.name].close()
                del self.pools[self.active_endpoint.name]
        except Exception as e:
            logger.error(f"Error closing pool during failover: {e}")
        
        self.active_endpoint = None
    
    async def _health_check_loop(self) -> None:
        """Background health check loop."""
        logger.info("❤️ Starting database health check loop")
        
        while self._initialized:
            try:
                await asyncio.sleep(self.config['health_check_interval'])
                await self._perform_health_check()
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
    
    async def _perform_health_check(self) -> Dict:
        """Perform health check on active connection."""
        if not self.active_endpoint:
            return {'status': 'no_active_endpoint'}
        
        try:
            start_time = time.time()
            
            async with self.get_connection() as conn:
                # Basic connectivity test
                await conn.fetchval('SELECT 1')
                
                # Get connection info
                version = await conn.fetchval('SELECT version()')
                current_db = await conn.fetchval('SELECT current_database()')
                connection_count = await conn.fetchval(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                )
            
            response_time = time.time() - start_time
            
            health_info = {
                'status': 'healthy',
                'endpoint': self.active_endpoint.name,
                'response_time': round(response_time, 3),
                'database_version': version.split()[1] if version else 'unknown',
                'database': current_db,
                'active_connections': connection_count,
                'timestamp': time.time()
            }
            
            # Add pool statistics
            if self.active_endpoint.name in self.pools:
                pool = self.pools[self.active_endpoint.name]
                health_info['pool'] = {
                    'size': pool.get_size(),
                    'idle': pool.get_idle_size(),
                    'max_size': pool.get_max_size(),
                    'min_size': pool.get_min_size()
                }
            
            if self.config['log_slow_queries'] and response_time > self.config['slow_query_threshold']:
                logger.warning(f"🐌 Slow health check: {response_time:.3f}s")
            
            return health_info
            
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            return {'status': 'unhealthy', 'error': str(e), 'timestamp': time.time()}
    
    async def execute_query(self, query: str, *args, **kwargs) -> any:
        """Execute a query with automatic retry and failover."""
        last_error = None
        
        for attempt in range(self.config['max_retry_attempts']):
            try:
                async with self.get_connection() as conn:
                    if args:
                        return await conn.fetchval(query, *args)
                    else:
                        return await conn.fetchval(query)
                        
            except Exception as e:
                last_error = e
                if attempt < self.config['max_retry_attempts'] - 1:
                    delay = min(
                        self.config['retry_base_delay'] * (2 ** attempt),
                        self.config['retry_max_delay']
                    )
                    logger.warning(f"Query failed (attempt {attempt + 1}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Query failed after {self.config['max_retry_attempts']} attempts: {e}")
        
        raise last_error
    
    def get_stats(self) -> Dict:
        """Get connection statistics."""
        stats = self.connection_stats.copy()
        stats['active_endpoint'] = self.active_endpoint.name if self.active_endpoint else None
        stats['pool_count'] = len(self.pools)
        stats['initialized'] = self._initialized
        
        # Add pool stats
        if self.active_endpoint and self.active_endpoint.name in self.pools:
            pool = self.pools[self.active_endpoint.name]
            stats['active_pool'] = {
                'size': pool.get_size(),
                'idle': pool.get_idle_size(),
                'max_size': pool.get_max_size(),
                'min_size': pool.get_min_size()
            }
        
        return stats
    
    async def close(self) -> None:
        """Close all database connections."""
        logger.info("🔄 Closing database connections...")
        
        self._initialized = False
        
        for name, pool in self.pools.items():
            try:
                await pool.close()
                logger.info(f"✅ Closed pool for {name}")
            except Exception as e:
                logger.error(f"Error closing pool {name}: {e}")
        
        self.pools.clear()
        self.active_endpoint = None
        logger.info("✅ All database connections closed")


def create_production_database_manager() -> ProductionDatabaseManager:
    """Create production database manager with Supabase endpoints."""
    
    # Supabase project details
    project_id = "emzlxdutmhmbvaetphpu"
    password = "b6Sfj*D!Gr98vPY"
    
    # Define endpoints in priority order
    endpoints = [
        # Primary: Connection pooler (recommended for production)
        DatabaseEndpoint(
            name="supabase_pooler",
            connection_type=ConnectionType.POOLER,
            host="aws-0-us-east-1.pooler.supabase.com",
            port=6543,
            database="postgres",
            username=f"postgres.{project_id}",
            password=password,
            priority=1
        ),
        
        # Secondary: Direct connection (fallback)
        DatabaseEndpoint(
            name="supabase_direct",
            connection_type=ConnectionType.DIRECT,
            host="aws-0-us-east-1.pooler.supabase.com",
            port=5432,
            database="postgres",
            username=f"postgres.{project_id}",
            password=password,
            priority=2
        )
    ]
    
    return ProductionDatabaseManager(endpoints)


# Async context manager for easy usage
@asynccontextmanager
async def get_production_database() -> AsyncGenerator[ProductionDatabaseManager, None]:
    """
    Context manager for production database access.
    
    Usage:
        async with get_production_database() as db:
            result = await db.execute_query("SELECT 1")
    """
    db_manager = create_production_database_manager()
    try:
        await db_manager.initialize()
        yield db_manager
    finally:
        await db_manager.close()


# Example usage and testing
async def test_production_database():
    """Test the production database configuration."""
    logger.info("🧪 Testing production database configuration...")
    
    async with get_production_database() as db:
        # Test basic query
        result = await db.execute_query("SELECT 1 as test")
        logger.info(f"✅ Basic query result: {result}")
        
        # Test database info
        version = await db.execute_query("SELECT version()")
        logger.info(f"📊 Database version: {version.split()[1] if version else 'unknown'}")
        
        # Test concurrent connections
        tasks = []
        for i in range(5):
            task = db.execute_query("SELECT NOW() as current_time")
            tasks.append(task)
        
        results = await asyncio.gather(*tasks)
        logger.info(f"✅ Concurrent queries completed: {len(results)} results")
        
        # Get statistics
        stats = db.get_stats()
        logger.info(f"📊 Connection stats: {stats}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_production_database())