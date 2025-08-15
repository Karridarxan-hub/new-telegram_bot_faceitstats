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
        
        # Initialize Redis cache (with fallback)
        redis_available = False
        try:
            logger.info("🔄 Initializing Redis cache...")
            await init_redis_cache(settings.redis_url)
            redis_available = True
            logger.info("✅ Redis cache connected successfully")
        except Exception as e:
            logger.warning(f"⚠️ Redis unavailable, using in-memory cache: {e}")
            redis_available = False
        
        # Initialize PostgreSQL database (with fallback)
        db_available = False
        try:
            logger.info("🐘 Initializing PostgreSQL database...")
            db_config = settings.get_database_config()
            await init_database(db_config)
            
            # Check database health
            db_health = await get_health_status()
            if db_health.get("connected", False):
                logger.info(f"✅ Database connected: PostgreSQL {db_health.get('version', 'unknown')}")
                db_available = True
            else:
                logger.warning(f"⚠️ Database health issue: {db_health.get('error', 'unknown')}")
                db_available = False
        except Exception as e:
            logger.warning(f"⚠️ PostgreSQL unavailable, using JSON storage: {e}")
            db_available = False
        
        # Log fallback status
        if not redis_available and not db_available:
            logger.info("📝 Running in lightweight mode with JSON storage and in-memory cache")
        elif not redis_available:
            logger.info("📝 Running with PostgreSQL and in-memory cache (Redis unavailable)")
        elif not db_available:
            logger.info("📝 Running with Redis cache and JSON storage (PostgreSQL unavailable)")
        else:
            logger.info("📝 Running in full enterprise mode with PostgreSQL and Redis")
        
        # Initialize bot and monitor
        bot = FaceitTelegramBot()
        monitor = MatchMonitor(bot)
        
        # Start monitor after a small delay
        async def start_monitor():
            await asyncio.sleep(5)
            await monitor.start()
        
        # Start bot and monitor
        await asyncio.gather(
            bot.start_polling(),
            start_monitor()
        )
    
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        # Close database connections (if they were established)
        try:
            logger.info("🐘 Closing database connections...")
            await close_database()
        except Exception as e:
            logger.debug(f"Database cleanup error (expected if not connected): {e}")
        
        # Close Redis connections (if they were established)
        try:
            logger.info("🔄 Closing Redis cache connections...")
            await close_redis_cache()
        except Exception as e:
            logger.debug(f"Redis cleanup error (expected if not connected): {e}")
        
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