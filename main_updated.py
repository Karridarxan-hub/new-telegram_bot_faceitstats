"""Main application entry point with service integration."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import settings, validate_settings
from config.version import get_version, get_build_info
from bot.bot import FaceitTelegramBot
from utils.monitor import MatchMonitor
from utils.storage import storage as legacy_storage
from utils.redis_cache import init_redis_cache, close_redis_cache
from database import init_database, close_database, get_health_status

# Service layer imports
from services.user import UserService
from services.subscription import SubscriptionService
from services.match import MatchService
from services.analytics import AnalyticsService
from services.cache import CacheService

# Repository imports
from database.repositories.user import UserRepository
from database.repositories.subscription import SubscriptionRepository
from database.repositories.match import MatchRepository
from database.repositories.analytics import AnalyticsRepository

# Integration adapters
from adapters.storage_adapter import StorageAdapter, StorageBackend
from adapters.migration_adapter import MigrationAdapter
from adapters.bot_integration import BotIntegrationAdapter

# FACEIT API
from faceit.api import FaceitAPI


def setup_logging():
    """Setup application logging."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('bot.log', encoding='utf-8')
        ]
    )
    
    # Reduce noise from HTTP libraries
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('aiogram').setLevel(logging.INFO)


async def initialize_services() -> tuple[
    Optional[UserService],
    Optional[SubscriptionService], 
    Optional[MatchService],
    Optional[AnalyticsService],
    Optional[CacheService]
]:
    """
    Initialize all services with error handling.
    
    Returns:
        Tuple of service instances (None if initialization fails)
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Initialize repositories
        user_repo = UserRepository()
        subscription_repo = SubscriptionRepository()
        match_repo = MatchRepository()
        analytics_repo = AnalyticsRepository()
        
        # Initialize FACEIT API
        faceit_api = FaceitAPI()
        
        # Initialize services
        user_service = UserService(
            user_repository=user_repo,
            subscription_repository=subscription_repo,
            faceit_api=faceit_api
        )
        
        subscription_service = SubscriptionService(
            subscription_repository=subscription_repo,
            user_repository=user_repo
        )
        
        match_service = MatchService(
            match_repository=match_repo,
            user_repository=user_repo,
            faceit_api=faceit_api
        )
        
        analytics_service = AnalyticsService(
            analytics_repository=analytics_repo,
            user_repository=user_repo,
            match_repository=match_repo
        )
        
        cache_service = CacheService()
        
        logger.info("✅ All services initialized successfully")
        
        return (
            user_service,
            subscription_service,
            match_service,
            analytics_service,
            cache_service
        )
    
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")
        logger.warning("📋 Will use fallback mode with JSON storage only")
        return None, None, None, None, None


async def setup_storage_adapter(
    user_service: Optional[UserService],
    subscription_service: Optional[SubscriptionService]
) -> StorageAdapter:
    """
    Setup storage adapter with appropriate backend.
    
    Args:
        user_service: User service instance or None
        subscription_service: Subscription service instance or None
        
    Returns:
        Configured storage adapter
    """
    logger = logging.getLogger(__name__)
    
    # Determine storage backend based on service availability and configuration
    if hasattr(settings, 'storage_backend'):
        backend = StorageBackend(settings.storage_backend)
    else:
        # Auto-detect based on service availability
        if user_service and subscription_service:
            backend = StorageBackend.DUAL  # Use both during transition
        else:
            backend = StorageBackend.JSON  # Fallback to JSON only
    
    logger.info(f"📦 Configuring storage adapter with backend: {backend.value}")
    
    storage_adapter = StorageAdapter(
        backend=backend,
        user_service=user_service,
        subscription_service=subscription_service
    )
    
    # Test storage adapter
    try:
        health = await storage_adapter.health_check()
        logger.info(f"✅ Storage adapter health check: {health['json_status']}, {health['postgresql_status']}")
    except Exception as e:
        logger.warning(f"⚠️ Storage adapter health check failed: {e}")
    
    return storage_adapter


async def setup_migration_adapter(
    user_service: Optional[UserService],
    subscription_service: Optional[SubscriptionService]
) -> Optional[MigrationAdapter]:
    """
    Setup migration adapter if services are available.
    
    Args:
        user_service: User service instance or None
        subscription_service: Subscription service instance or None
        
    Returns:
        Migration adapter or None if services not available
    """
    if not user_service or not subscription_service:
        return None
    
    logger = logging.getLogger(__name__)
    
    try:
        user_repo = UserRepository()
        subscription_repo = SubscriptionRepository()
        
        migration_adapter = MigrationAdapter(
            user_service=user_service,
            subscription_service=subscription_service,
            user_repository=user_repo,
            subscription_repository=subscription_repo
        )
        
        logger.info("✅ Migration adapter initialized")
        return migration_adapter
    
    except Exception as e:
        logger.error(f"❌ Failed to initialize migration adapter: {e}")
        return None


async def run_initial_migration(
    migration_adapter: Optional[MigrationAdapter],
    auto_migrate: bool = False
) -> bool:
    """
    Run initial migration if requested and needed.
    
    Args:
        migration_adapter: Migration adapter instance
        auto_migrate: Whether to automatically migrate data
        
    Returns:
        Success status
    """
    if not migration_adapter:
        return True
    
    logger = logging.getLogger(__name__)
    
    try:
        # Check if migration is needed
        integrity_result = await migration_adapter.validate_migration_integrity()
        
        json_users = integrity_result.get('total_json_users', 0)
        pg_users = integrity_result.get('total_postgresql_users', 0)
        integrity_score = integrity_result.get('integrity_score', 100)
        
        logger.info(f"📊 Migration status: JSON={json_users}, PG={pg_users}, Integrity={integrity_score}%")
        
        # Auto-migrate if enabled and needed
        if auto_migrate and json_users > pg_users and integrity_score < 90:
            logger.info("🔄 Starting automatic migration from JSON to PostgreSQL...")
            
            result = await migration_adapter.migrate_all_users(
                direction=MigrationDirection.JSON_TO_POSTGRESQL,
                batch_size=25,
                validation_mode=True
            )
            
            if result.status == MigrationStatus.COMPLETED:
                logger.info(f"✅ Migration completed: {result.migrated_users}/{result.total_users} users migrated")
            else:
                logger.warning(f"⚠️ Migration partially completed: {result.migrated_users}/{result.total_users} users migrated")
                if result.errors:
                    for error in result.errors[:5]:  # Log first 5 errors
                        logger.error(f"Migration error: {error}")
            
            return result.status in [MigrationStatus.COMPLETED]
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Error during migration: {e}")
        return False


async def setup_bot_integration(
    storage_adapter: StorageAdapter,
    services: tuple
) -> BotIntegrationAdapter:
    """
    Setup bot integration adapter.
    
    Args:
        storage_adapter: Storage adapter instance
        services: Tuple of service instances
        
    Returns:
        Bot integration adapter
    """
    logger = logging.getLogger(__name__)
    
    user_service, subscription_service, match_service, analytics_service, _ = services
    
    bot_adapter = BotIntegrationAdapter(
        storage_adapter=storage_adapter,
        user_service=user_service,
        subscription_service=subscription_service,
        match_service=match_service,
        analytics_service=analytics_service,
        faceit_api=FaceitAPI()
    )
    
    logger.info("✅ Bot integration adapter initialized")
    
    # Test integration adapter
    try:
        service_info = bot_adapter.get_service_info()
        logger.info(f"📋 Service availability: {service_info['service_availability']}")
    except Exception as e:
        logger.warning(f"⚠️ Bot integration adapter test failed: {e}")
    
    return bot_adapter


async def main():
    """Main application function with service integration."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Show version info
        build_info = get_build_info()
        version = get_version()
        
        logger.info(f"🚀 Starting {build_info['name']} v{version}")
        logger.info(f"📋 {build_info['description']}")
        logger.info(f"🐍 Python: {build_info['python_version']}")
        logger.info(f"🐳 Docker: {build_info['docker_ready']}")
        
        # Validate configuration
        validate_settings()
        logger.info("✅ Configuration validated successfully")
        
        # Initialize Redis cache
        logger.info("🔄 Initializing Redis cache...")
        try:
            await init_redis_cache(settings.redis_url)
            logger.info("✅ Redis cache initialized")
        except Exception as e:
            logger.warning(f"⚠️ Redis cache initialization failed: {e}")
            logger.info("📋 Continuing without Redis cache")
        
        # Initialize PostgreSQL database
        logger.info("🐘 Initializing PostgreSQL database...")
        try:
            db_config = settings.get_database_config()
            await init_database(db_config)
            
            # Check database health
            db_health = await get_health_status()
            if db_health.get("connected", False):
                logger.info(f"✅ Database connected: PostgreSQL {db_health.get('version', 'unknown')}")
            else:
                logger.warning(f"⚠️ Database health issue: {db_health.get('error', 'unknown')}")
                logger.info("📋 Will use JSON storage as fallback")
        except Exception as e:
            logger.warning(f"⚠️ PostgreSQL initialization failed: {e}")
            logger.info("📋 Will use JSON storage only")
        
        # Initialize services
        logger.info("🔧 Initializing services...")
        services = await initialize_services()
        user_service, subscription_service, match_service, analytics_service, cache_service = services
        
        # Setup storage adapter
        logger.info("📦 Setting up storage adapter...")
        storage_adapter = await setup_storage_adapter(user_service, subscription_service)
        
        # Setup migration adapter
        logger.info("🔄 Setting up migration adapter...")
        migration_adapter = await setup_migration_adapter(user_service, subscription_service)
        
        # Run initial migration if needed
        auto_migrate = getattr(settings, 'auto_migrate', False)
        if auto_migrate:
            logger.info("🔄 Running initial migration check...")
            migration_success = await run_initial_migration(migration_adapter, auto_migrate)
            if migration_success:
                logger.info("✅ Migration completed successfully")
            else:
                logger.warning("⚠️ Migration completed with issues")
        
        # Setup bot integration
        logger.info("🤖 Setting up bot integration...")
        bot_adapter = await setup_bot_integration(storage_adapter, services)
        
        # Initialize bot with integration adapter
        bot = FaceitTelegramBot(integration_adapter=bot_adapter)
        
        # Initialize monitor with storage adapter
        monitor = MatchMonitor(bot, storage_adapter)
        
        # Start monitor after a small delay
        async def start_monitor():
            await asyncio.sleep(5)
            await monitor.start()
        
        # Periodic subscription check task
        async def subscription_checker():
            while True:
                try:
                    await asyncio.sleep(3600)  # Check every hour
                    
                    # Use storage adapter for subscription checks
                    if hasattr(storage_adapter.storage, 'check_expired_subscriptions'):
                        expired_users = await storage_adapter.storage.check_expired_subscriptions()
                        if expired_users:
                            logger.info(f"⏰ Downgraded {len(expired_users)} expired subscriptions")
                    
                except Exception as e:
                    logger.error(f"❌ Error checking subscriptions: {e}")
        
        # System health monitoring task
        async def health_monitor():
            while True:
                try:
                    await asyncio.sleep(300)  # Check every 5 minutes
                    
                    health = await bot_adapter.health_check()
                    
                    # Log any health issues
                    storage_health = health.get("storage_adapter", {})
                    if storage_health.get("json_status") != "healthy":
                        logger.warning(f"⚠️ JSON storage health: {storage_health.get('json_status')}")
                    
                    if storage_health.get("postgresql_status") not in ["healthy", "not_available"]:
                        logger.warning(f"⚠️ PostgreSQL health: {storage_health.get('postgresql_status')}")
                    
                except Exception as e:
                    logger.error(f"❌ Error in health monitoring: {e}")
        
        logger.info("🚀 Starting bot and background tasks...")
        
        # Start bot, monitor, and background tasks
        await asyncio.gather(
            bot.start_polling(),
            start_monitor(),
            subscription_checker(),
            health_monitor()
        )
    
    except KeyboardInterrupt:
        logger.info("⏹️ Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")
        sys.exit(1)
    finally:
        # Close database connections
        logger.info("🐘 Closing database connections...")
        try:
            await close_database()
        except Exception as e:
            logger.warning(f"⚠️ Error closing database: {e}")
        
        # Close Redis connections
        logger.info("🔄 Closing Redis cache connections...")
        try:
            await close_redis_cache()
        except Exception as e:
            logger.warning(f"⚠️ Error closing Redis cache: {e}")
        
        # Stop monitor
        if 'monitor' in locals():
            try:
                await monitor.stop()
            except Exception as e:
                logger.warning(f"⚠️ Error stopping monitor: {e}")
        
        # Stop bot
        if 'bot' in locals():
            try:
                await bot.stop()
            except Exception as e:
                logger.warning(f"⚠️ Error stopping bot: {e}")
        
        logger.info("👋 Shutdown completed")


def graceful_shutdown():
    """Handle graceful shutdown."""
    logger = logging.getLogger(__name__)
    logger.info("🛑 Shutting down gracefully...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        graceful_shutdown()
    except Exception as e:
        logging.error(f"💥 Failed to start application: {e}")
        sys.exit(1)