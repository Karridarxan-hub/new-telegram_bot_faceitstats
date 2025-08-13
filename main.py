"""Main application entry point."""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import settings, validate_settings
from bot.bot import FaceitTelegramBot
from utils.monitor import MatchMonitor


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
        # Validate configuration
        validate_settings()
        logger.info("🚀 Starting FACEIT Stats Bot...")
        
        # Initialize bot and monitor
        bot = FaceitTelegramBot()
        monitor = MatchMonitor(bot)
        
        # Start monitor after a small delay
        async def start_monitor():
            await asyncio.sleep(5)
            await monitor.start()
        
        # Start both bot and monitor
        await asyncio.gather(
            bot.start_polling(),
            start_monitor()
        )
    
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)
    finally:
        if 'monitor' in locals():
            await monitor.stop()
        if 'bot' in locals():
            await bot.stop()


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
        logging.error(f"Failed to start application: {e}")
        sys.exit(1)