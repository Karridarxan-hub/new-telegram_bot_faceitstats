"""
Database-specific configuration for PostgreSQL integration.

This module provides:
- Environment-based database configuration
- Connection pooling settings
- Performance optimization parameters
- Development vs Production configurations
- Migration and backup settings
"""

import os
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class DatabaseEnvironment(str, Enum):
    """Database environment types."""
    DEVELOPMENT = "development" 
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class DatabaseConfig(BaseModel):
    """Database configuration with environment-specific optimizations."""
    
    # Connection settings
    database_url: str = Field(..., description="Database connection URL")
    environment: DatabaseEnvironment = Field(
        default=DatabaseEnvironment.PRODUCTION,
        description="Database environment"
    )
    
    # Connection pool settings
    pool_size: int = Field(default=20, ge=1, le=100, description="Connection pool size")
    pool_overflow: int = Field(default=30, ge=0, le=100, description="Pool overflow connections")
    pool_timeout: int = Field(default=30, ge=1, le=300, description="Pool checkout timeout (seconds)")
    pool_recycle: int = Field(default=3600, ge=300, le=86400, description="Connection recycle time (seconds)")
    enable_connection_pooling: bool = Field(default=True, description="Enable connection pooling")
    
    # Performance settings
    echo_sql: bool = Field(default=False, description="Log SQL statements")
    command_timeout: int = Field(default=60, ge=1, le=600, description="Command timeout (seconds)")
    connection_timeout: int = Field(default=30, ge=5, le=120, description="Connection timeout (seconds)")
    
    # Retry settings
    max_retries: int = Field(default=3, ge=1, le=10, description="Maximum connection retries")
    retry_interval: float = Field(default=1.0, ge=0.1, le=30.0, description="Retry interval (seconds)")
    retry_delay: float = Field(default=1.0, ge=0.1, le=30.0, description="Retry delay (seconds)")
    
    # Pool settings (additional)
    enable_pool: bool = Field(default=True, description="Enable database connection pooling")
    
    # Monitoring settings
    connection_monitoring: bool = Field(default=True, description="Enable connection monitoring")
    log_slow_queries: bool = Field(default=True, description="Log slow queries")
    slow_query_threshold: float = Field(default=1.0, ge=0.1, le=60.0, description="Slow query threshold (seconds)")
    
    # Migration settings
    enable_migrations: bool = Field(default=True, description="Enable automatic migrations")
    migration_timeout: int = Field(default=300, ge=30, le=3600, description="Migration timeout (seconds)")
    
    # Backup and maintenance
    enable_backup: bool = Field(default=False, description="Enable backup features")
    backup_retention_days: int = Field(default=30, ge=1, le=365, description="Backup retention (days)")
    
    # Cache integration
    enable_query_cache: bool = Field(default=True, description="Enable query result caching")
    default_cache_ttl: int = Field(default=300, ge=60, le=3600, description="Default cache TTL (seconds)")
    
    @field_validator('database_url')
    @classmethod
    def validate_database_url(cls, v):
        """Validate database URL format."""
        if not v.startswith(('postgresql://', 'postgresql+asyncpg://')):
            # Auto-add asyncpg driver if not specified
            if v.startswith('postgresql://'):
                v = v.replace('postgresql://', 'postgresql+asyncpg://', 1)
            else:
                raise ValueError("DATABASE_URL must start with postgresql:// or postgresql+asyncpg://")
        return v
    
    def get_sqlalchemy_url(self) -> str:
        """Get SQLAlchemy-compatible URL."""
        return self.database_url
    
    def get_connection_params(self) -> Dict[str, Any]:
        """Get connection parameters for SQLAlchemy engine."""
        params = {
            'echo': self.echo_sql,
            'pool_size': self.pool_size if self.enable_connection_pooling else 0,
            'pool_timeout': self.pool_timeout,
            'pool_recycle': self.pool_recycle,
            'connect_args': {
                'command_timeout': self.command_timeout,
                'server_settings': {
                    'application_name': 'faceit_telegram_bot',
                    'jit': 'off',  # Disable JIT for faster connection
                }
            }
        }
        
        if self.enable_connection_pooling:
            params['max_overflow'] = self.pool_overflow
        else:
            params['poolclass'] = 'NullPool'
            
        return params
    
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == DatabaseEnvironment.DEVELOPMENT
        
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == DatabaseEnvironment.PRODUCTION
    
    class Config:
        """Pydantic config."""
        use_enum_values = True
        case_sensitive = False


def create_database_config_from_env() -> DatabaseConfig:
    """Create database config from environment variables."""
    return DatabaseConfig(
        database_url=os.getenv('DATABASE_URL', 'postgresql+asyncpg://localhost/faceit_bot'),
        environment=DatabaseEnvironment(os.getenv('DB_ENVIRONMENT', 'production')),
        pool_size=int(os.getenv('DB_POOL_SIZE', 20)),
        pool_overflow=int(os.getenv('DB_POOL_OVERFLOW', 30)),
        echo_sql=os.getenv('DB_ECHO_SQL', 'false').lower() == 'true',
        max_retries=int(os.getenv('DB_MAX_RETRIES', 3)),
        enable_backup=os.getenv('DB_ENABLE_BACKUP', 'false').lower() == 'true',
    )


def validate_database_config(config: DatabaseConfig) -> bool:
    """Validate database configuration."""
    try:
        # Test URL parsing
        from urllib.parse import urlparse
        parsed = urlparse(config.database_url)
        if not parsed.scheme or not parsed.hostname:
            return False
        return True
    except Exception:
        return False


# Default configuration for testing
def get_test_config() -> DatabaseConfig:
    """Get test database configuration."""
    return DatabaseConfig(
        database_url='postgresql+asyncpg://test:test@localhost/test_db',
        environment=DatabaseEnvironment.TESTING,
        pool_size=1,
        pool_overflow=0,
        echo_sql=False,
        enable_connection_pooling=False,
        enable_backup=False,
    )