"""Configuration settings for FACEIT Telegram Bot with service integration."""

import os
from enum import Enum
from pydantic import Field, validator
from pydantic_settings import BaseSettings
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from config.database import DatabaseConfig


class StorageBackend(str, Enum):
    """Storage backend options."""
    JSON = "json"
    POSTGRESQL = "postgresql"
    DUAL = "dual"


class MigrationMode(str, Enum):
    """Migration mode options."""
    DISABLED = "disabled"
    MANUAL = "manual"
    AUTO = "auto"


class Settings(BaseSettings):
    """Application settings with service integration support."""
    
    # Telegram Bot configuration
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(None, env="TELEGRAM_CHAT_ID")
    
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
    redis_url: str = Field("redis://redis:6379", env="REDIS_URL")
    redis_password: Optional[str] = Field(None, env="REDIS_PASSWORD")
    redis_max_connections: int = Field(10, env="REDIS_MAX_CONNECTIONS")
    
    # Cache TTL settings
    cache_ttl_player: int = Field(300, env="CACHE_TTL_PLAYER")  # 5 minutes
    cache_ttl_match: int = Field(120, env="CACHE_TTL_MATCH")    # 2 minutes
    cache_ttl_stats: int = Field(600, env="CACHE_TTL_STATS")    # 10 minutes
    
    # Database settings (Phase 2-3) - PostgreSQL Integration
    database_url: Optional[str] = Field(None, env="DATABASE_URL")
    db_environment: str = Field("production", env="DB_ENVIRONMENT")
    db_pool_size: int = Field(20, env="DB_POOL_SIZE")
    db_pool_overflow: int = Field(30, env="DB_POOL_OVERFLOW")
    db_pool_timeout: int = Field(30, env="DB_POOL_TIMEOUT")
    db_max_retries: int = Field(3, env="DB_MAX_RETRIES")
    db_echo_sql: bool = Field(False, env="DB_ECHO_SQL")
    db_backup_enabled: bool = Field(True, env="DB_BACKUP_ENABLED")
    
    # Storage integration settings
    storage_backend: StorageBackend = Field(StorageBackend.JSON, env="STORAGE_BACKEND")
    migration_mode: MigrationMode = Field(MigrationMode.DISABLED, env="MIGRATION_MODE")
    auto_migrate: bool = Field(False, env="AUTO_MIGRATE")
    migration_batch_size: int = Field(50, env="MIGRATION_BATCH_SIZE")
    
    # Service integration settings
    enable_services: bool = Field(True, env="ENABLE_SERVICES")
    service_fallback_enabled: bool = Field(True, env="SERVICE_FALLBACK_ENABLED")
    health_check_interval: int = Field(300, env="HEALTH_CHECK_INTERVAL")  # 5 minutes
    
    # Performance and scaling settings
    max_concurrent_requests: int = Field(100, env="MAX_CONCURRENT_REQUESTS")
    request_timeout: int = Field(30, env="REQUEST_TIMEOUT")
    retry_attempts: int = Field(3, env="RETRY_ATTEMPTS")
    
    # Feature flags
    enable_match_analysis: bool = Field(True, env="ENABLE_MATCH_ANALYSIS")
    enable_subscription_system: bool = Field(True, env="ENABLE_SUBSCRIPTION_SYSTEM")
    enable_referral_system: bool = Field(True, env="ENABLE_REFERRAL_SYSTEM")
    enable_analytics: bool = Field(True, env="ENABLE_ANALYTICS")
    
    # Security settings
    admin_user_ids: Optional[str] = Field(None, env="ADMIN_USER_IDS")  # Comma-separated list
    rate_limit_enabled: bool = Field(True, env="RATE_LIMIT_ENABLED")
    max_requests_per_minute: int = Field(30, env="MAX_REQUESTS_PER_MINUTE")
    
    @validator("storage_backend", pre=True)
    def validate_storage_backend(cls, v):
        """Validate storage backend setting."""
        if isinstance(v, str):
            try:
                return StorageBackend(v.lower())
            except ValueError:
                raise ValueError(f"Invalid storage backend: {v}. Must be one of: {list(StorageBackend)}")
        return v
    
    @validator("migration_mode", pre=True)
    def validate_migration_mode(cls, v):
        """Validate migration mode setting."""
        if isinstance(v, str):
            try:
                return MigrationMode(v.lower())
            except ValueError:
                raise ValueError(f"Invalid migration mode: {v}. Must be one of: {list(MigrationMode)}")
        return v
    
    @validator("admin_user_ids")
    def validate_admin_user_ids(cls, v):
        """Parse admin user IDs from comma-separated string."""
        if v:
            try:
                # Convert to list of integers
                return [int(user_id.strip()) for user_id in v.split(",") if user_id.strip()]
            except ValueError as e:
                raise ValueError(f"Invalid admin user IDs format: {e}")
        return []
    
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
    
    def should_auto_migrate(self) -> bool:
        """Check if automatic migration should be performed."""
        return (
            self.migration_mode == MigrationMode.AUTO or 
            self.auto_migrate
        ) and self.enable_services
    
    def should_use_services(self) -> bool:
        """Check if services should be used."""
        return (
            self.enable_services and 
            self.storage_backend in [StorageBackend.POSTGRESQL, StorageBackend.DUAL]
        )
    
    def get_admin_user_ids(self) -> list[int]:
        """Get list of admin user IDs."""
        if isinstance(self.admin_user_ids, list):
            return self.admin_user_ids
        elif isinstance(self.admin_user_ids, str):
            try:
                return [int(user_id.strip()) for user_id in self.admin_user_ids.split(",") if user_id.strip()]
            except ValueError:
                return []
        return []
    
    def get_feature_flags(self) -> dict[str, bool]:
        """Get feature flags as dictionary."""
        return {
            "match_analysis": self.enable_match_analysis,
            "subscription_system": self.enable_subscription_system,
            "referral_system": self.enable_referral_system,
            "analytics": self.enable_analytics,
            "services": self.enable_services,
            "rate_limiting": self.rate_limit_enabled
        }
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        use_enum_values = True


# Global settings instance
settings = Settings()


def validate_settings() -> None:
    """Validate required settings and configuration consistency."""
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    if not settings.faceit_api_key:
        raise ValueError("FACEIT_API_KEY is required")
    
    # Validate database settings if DATABASE_URL is provided or PostgreSQL backend is used
    if settings.database_url or settings.storage_backend in [StorageBackend.POSTGRESQL, StorageBackend.DUAL]:
        try:
            db_config = settings.get_database_config()
            print(f"✅ Database configuration loaded: {db_config.environment.value} environment")
            
            if not settings.database_url:
                print("⚠️ Warning: PostgreSQL backend selected but DATABASE_URL not configured")
                print("📋 Will attempt to use default connection or fall back to JSON storage")
        except Exception as e:
            print(f"⚠️ Warning: Database configuration validation failed: {e}")
            if settings.storage_backend == StorageBackend.POSTGRESQL:
                raise ValueError(f"PostgreSQL backend requires valid database configuration: {e}")
    
    # Validate storage backend consistency
    if settings.storage_backend == StorageBackend.POSTGRESQL and not settings.enable_services:
        print("⚠️ Warning: PostgreSQL backend requires services to be enabled")
        print("📋 Automatically enabling services for PostgreSQL backend")
        settings.enable_services = True
    
    # Validate migration settings
    if settings.migration_mode == MigrationMode.AUTO and not settings.should_use_services():
        print("⚠️ Warning: Auto migration requires services and PostgreSQL backend")
        print("📋 Disabling auto migration")
        settings.migration_mode = MigrationMode.DISABLED
    
    # Validate performance settings
    if settings.migration_batch_size < 1 or settings.migration_batch_size > 1000:
        print("⚠️ Warning: Invalid migration batch size, using default (50)")
        settings.migration_batch_size = 50
    
    if settings.max_concurrent_requests < 1:
        print("⚠️ Warning: Invalid max concurrent requests, using default (100)")
        settings.max_concurrent_requests = 100
    
    # Show configuration summary
    print(f"📦 Storage Backend: {settings.storage_backend.value}")
    print(f"🔧 Services Enabled: {settings.enable_services}")
    print(f"🔄 Migration Mode: {settings.migration_mode.value}")
    print(f"🚀 Feature Flags: {sum(settings.get_feature_flags().values())}/{len(settings.get_feature_flags())} enabled")
    
    print("✅ Configuration validated successfully")


def get_environment_template() -> str:
    """Get environment template with all available settings."""
    return """
# FACEIT Telegram Bot Configuration

# Required Settings
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
FACEIT_API_KEY=your_faceit_api_key_here

# Optional Telegram Settings
TELEGRAM_CHAT_ID=your_chat_id_for_notifications

# Database Settings (PostgreSQL)
DATABASE_URL=postgresql://user:password@localhost:5432/faceit_bot
DB_ENVIRONMENT=production
DB_POOL_SIZE=20
DB_POOL_OVERFLOW=30

# Redis Cache Settings
REDIS_URL=redis://localhost:6379
REDIS_PASSWORD=your_redis_password
REDIS_MAX_CONNECTIONS=10

# Storage Integration
STORAGE_BACKEND=dual  # json, postgresql, dual
MIGRATION_MODE=manual  # disabled, manual, auto
AUTO_MIGRATE=false
MIGRATION_BATCH_SIZE=50

# Service Integration
ENABLE_SERVICES=true
SERVICE_FALLBACK_ENABLED=true
HEALTH_CHECK_INTERVAL=300

# Feature Flags
ENABLE_MATCH_ANALYSIS=true
ENABLE_SUBSCRIPTION_SYSTEM=true
ENABLE_REFERRAL_SYSTEM=true
ENABLE_ANALYTICS=true

# Performance Settings
MAX_CONCURRENT_REQUESTS=100
REQUEST_TIMEOUT=30
RETRY_ATTEMPTS=3

# Security Settings
ADMIN_USER_IDS=123456789,987654321
RATE_LIMIT_ENABLED=true
MAX_REQUESTS_PER_MINUTE=30

# Cache TTL (seconds)
CACHE_TTL_PLAYER=300
CACHE_TTL_MATCH=120
CACHE_TTL_STATS=600

# Monitoring
CHECK_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
"""


def create_env_file(filename: str = ".env.example") -> None:
    """Create environment file template."""
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(get_environment_template().strip())
    print(f"📝 Environment template created: {filename}")


if __name__ == "__main__":
    # Create environment template when run directly
    create_env_file()
    
    # Test configuration validation
    try:
        validate_settings()
    except ValueError as e:
        print(f"❌ Configuration validation failed: {e}")
        print("📋 Please check your environment variables")