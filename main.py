"""Main application entry point."""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import settings, validate_settings
from config.version import get_version, get_build_info
from bot.bot import FaceitTelegramBot
from utils.monitor import MatchMonitor
from utils.storage import storage
from utils.redis_cache import init_redis_cache, close_redis_cache
from database import init_database, close_database, get_health_status


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


async def main():
    """Main application function."""
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
        logger.info("Configuration validated successfully")
        
        # Initialize Redis cache
        logger.info("🔄 Initializing Redis cache...")
        await init_redis_cache(settings.redis_url)
        
        # Initialize PostgreSQL database
        logger.info("🐘 Initializing PostgreSQL database...")
        db_config = settings.get_database_config()
        await init_database(db_config)
        
        # Check database health
        db_health = await get_health_status()
        if db_health.get("connected", False):
            logger.info(f"✅ Database connected: PostgreSQL {db_health.get('version', 'unknown')}")
        else:
            logger.warning(f"⚠️ Database health issue: {db_health.get('error', 'unknown')}")
        
        # Initialize bot and monitor
        bot = FaceitTelegramBot()
        monitor = MatchMonitor(bot)
        
        # Start monitor after a small delay
        async def start_monitor():
            await asyncio.sleep(5)
            await monitor.start()
        
        # Periodic subscription check task
        async def subscription_checker():
            while True:
                try:
                    await asyncio.sleep(3600)  # Check every hour
                    expired_users = await storage.check_expired_subscriptions()
                    if expired_users:
                        logger.info(f"Downgraded {len(expired_users)} expired subscriptions")
                except Exception as e:
                    logger.error(f"Error checking subscriptions: {e}")
        
        # Start bot, monitor, and subscription checker
        await asyncio.gather(
            bot.start_polling(),
            start_monitor(),
            subscription_checker()
        )
    
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        # Close database connections
        logger.info("🐘 Closing database connections...")
        await close_database()
        
        # Close Redis connections
        logger.info("🔄 Closing Redis cache connections...")
        await close_redis_cache()
        
        if 'monitor' in locals():
            await monitor.stop()
        if 'bot' in locals():
            await bot.stop()


def graceful_shutdown():
    """Handle graceful shutdown."""
    logger = logging.getLogger(__name__)
    logger.info("Shutting down gracefully...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        graceful_shutdown()
    except Exception as e:
        logging.error(f"Failed to start application: {e}")
        sys.exit(1)