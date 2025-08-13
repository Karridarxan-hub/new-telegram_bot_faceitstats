"""Main bot implementation."""

import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config.settings import settings
from .handlers import router
from faceit.api import FaceitAPI
from utils.storage import storage
from utils.formatter import MessageFormatter

logger = logging.getLogger(__name__)


class FaceitTelegramBot:
    """FACEIT Telegram Bot."""
    
    def __init__(self):
        # Initialize bot with default properties
        default_properties = DefaultBotProperties(
            parse_mode=ParseMode.MARKDOWN_V2
        )
        
        self.bot = Bot(
            token=settings.telegram_bot_token,
            default=default_properties
        )
        self.dp = Dispatcher()
        self.faceit_api = FaceitAPI()
        
        # Include handlers
        self.dp.include_router(router)
        
        logger.info("Bot initialized successfully")
    
    async def send_match_notification(self, user_id: int, match_id: str) -> None:
        """Send match notification to user."""
        try:
            user = await storage.get_user(user_id)
            if not user or not user.faceit_player_id:
                logger.warning(f"User {user_id} not found or no FACEIT ID")
                return
            
            # Get match details
            match = await self.faceit_api.get_match_details(match_id)
            if not match or match.status != "FINISHED":
                logger.info(f"Match {match_id} not finished yet")
                return
            
            # Get match statistics
            stats = await self.faceit_api.get_match_stats(match_id)
            
            # Format message
            formatted_message = MessageFormatter.format_match_result(
                match, stats, user.faceit_player_id
            )
            
            # Send notification
            notification_text = f"🔔 **Новый завершенный матч\\!**\\n\\n{formatted_message}"
            
            await self.bot.send_message(
                chat_id=user_id,
                text=notification_text,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            
            # Update last checked match
            await storage.update_last_checked_match(user_id, match_id)
            
            logger.info(f"Sent match notification to user {user_id} for match {match_id}")
            
        except Exception as e:
            logger.error(f"Error sending match notification to {user_id}: {e}")
    
    async def start_polling(self) -> None:
        """Start bot polling."""
        logger.info("Starting bot polling...")
        await self.dp.start_polling(self.bot)
    
    async def stop(self) -> None:
        """Stop bot."""
        logger.info("Stopping bot...")
        await self.bot.session.close()