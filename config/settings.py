"""Configuration settings for FACEIT Telegram Bot."""

import os
from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config.database import DatabaseConfig


class Settings(BaseSettings):
    """Application settings."""
    
    # Telegram Bot configuration
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(None, env="TELEGRAM_CHAT_ID")
    admin_user_ids: Optional[str] = Field(None, env="ADMIN_USER_IDS")
    
    # FACEIT API configuration
    faceit_api_key: str = Field(..., env="FACEIT_API_KEY")
    faceit_api_base_url: str = Field(
        "https://open.faceit.com/data/v4", 
        env="FACEIT_API_BASE_URL"
    )
    
    # Monitoring settings
    check_interval_minutes: int = Field(10, env="CHECK_INTERVAL_MINUTES")
    
    # Logging
    log_level: str = Field("INFO", env="LOG_LEVEL")
    
    # Data storage
    data_file_path: str = Field("data.json", env="DATA_FILE_PATH")
    
    # Redis configuration (Phase 1)
    redis_url: str = Field("redis://localhost:6379", env="REDIS_URL")
    redis_password: Optional[str] = Field(None, env="REDIS_PASSWORD")
    redis_max_connections: int = Field(10, env="REDIS_MAX_CONNECTIONS")
    
    # Cache TTL settings
    cache_ttl_player: int = Field(300, env="CACHE_TTL_PLAYER")  # 5 minutes
    cache_ttl_match: int = Field(120, env="CACHE_TTL_MATCH")    # 2 minutes
    cache_ttl_stats: int = Field(600, env="CACHE_TTL_STATS")    # 10 minutes
    
    # Queue system settings (Phase 5)
    queue_default_timeout: int = Field(300, env="QUEUE_DEFAULT_TIMEOUT")  # 5 minutes
    queue_high_priority_timeout: int = Field(180, env="QUEUE_HIGH_PRIORITY_TIMEOUT")  # 3 minutes
    queue_low_priority_timeout: int = Field(600, env="QUEUE_LOW_PRIORITY_TIMEOUT")  # 10 minutes
    queue_max_workers: int = Field(4, env="QUEUE_MAX_WORKERS")
    queue_worker_ttl: int = Field(420, env="QUEUE_WORKER_TTL")  # 7 minutes
    queue_monitoring_interval: int = Field(30, env="QUEUE_MONITORING_INTERVAL")  # 30 seconds
    queue_max_retries: int = Field(3, env="QUEUE_MAX_RETRIES")
    queue_result_ttl: int = Field(3600, env="QUEUE_RESULT_TTL")  # 1 hour
    queue_failure_ttl: int = Field(86400, env="QUEUE_FAILURE_TTL")  # 24 hours
    queue_connection_pool_size: int = Field(20, env="QUEUE_CONNECTION_POOL_SIZE")
    queue_burst_timeout: int = Field(60, env="QUEUE_BURST_TIMEOUT")
    queue_enable_monitoring: bool = Field(True, env="QUEUE_ENABLE_MONITORING")
    queue_metrics_retention_days: int = Field(7, env="QUEUE_METRICS_RETENTION_DAYS")
    queue_dashboard_enabled: bool = Field(True, env="QUEUE_DASHBOARD_ENABLED")
    queue_dashboard_port: int = Field(9181, env="QUEUE_DASHBOARD_PORT")
    
    # Database settings (Phase 2-3) - PostgreSQL Integration
    database_url: Optional[str] = Field(None, env="DATABASE_URL")
    db_environment: str = Field("production", env="DB_ENVIRONMENT")
    db_pool_size: int = Field(20, env="DB_POOL_SIZE")
    db_pool_overflow: int = Field(30, env="DB_POOL_OVERFLOW")
    db_pool_timeout: int = Field(30, env="DB_POOL_TIMEOUT")
    db_max_retries: int = Field(3, env="DB_MAX_RETRIES")
    db_echo_sql: bool = Field(False, env="DB_ECHO_SQL")
    db_backup_enabled: bool = Field(True, env="DB_BACKUP_ENABLED")
    
    def get_database_config(self) -> "DatabaseConfig":
        """Get database configuration from main settings."""
        from config.database import DatabaseConfig, DatabaseEnvironment
        
        # Map environment string to enum
        env_mapping = {
            "development": DatabaseEnvironment.DEVELOPMENT,
            "testing": DatabaseEnvironment.TESTING, 
            "staging": DatabaseEnvironment.STAGING,
            "production": DatabaseEnvironment.PRODUCTION,
        }
        environment = env_mapping.get(self.db_environment.lower(), DatabaseEnvironment.PRODUCTION)
        
        return DatabaseConfig(
            environment=environment,
            database_url=self.database_url or os.getenv("DATABASE_URL", ""),
            pool_size=self.db_pool_size,
            pool_overflow=self.db_pool_overflow,
            pool_timeout=self.db_pool_timeout,
            max_retries=self.db_max_retries,
            echo_sql=self.db_echo_sql,
            backup_enabled=self.db_backup_enabled,
        )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
settings = Settings()


def validate_settings() -> None:
    """Validate required settings."""
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    if not settings.faceit_api_key:
        raise ValueError("FACEIT_API_KEY is required")
    
    # Validate database settings if DATABASE_URL is provided
    if settings.database_url:
        try:
            db_config = settings.get_database_config()
            print(f"Database configuration loaded: {db_config.environment.value} environment")
        except Exception as e:
            print(f"Warning: Database configuration validation failed: {e}")
    
    print("Configuration validated successfully")