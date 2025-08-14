"""Match monitoring utilities."""

import asyncio
import logging
from typing import List

from faceit.api import FaceitAPI
from utils.storage import storage
from config.settings import settings

logger = logging.getLogger(__name__)


class MatchMonitor:
    """Monitor new matches for all users."""
    
    def __init__(self, bot):
        self.bot = bot
        self.faceit_api = FaceitAPI()
        self.is_running = False
        self.monitor_task = None
    
    async def start(self) -> None:
        """Start monitoring matches."""
        if self.is_running:
            logger.warning("Monitor already running")
            return
        
        self.is_running = True
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        
        logger.info(
            f"✅ Match monitor started with {settings.check_interval_minutes} minute intervals"
        )
    
    async def stop(self) -> None:
        """Stop monitoring matches."""
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        logger.info("⏹️ Match monitor stopped")
    
    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self.is_running:
            try:
                await self._check_all_users()
            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
            
            # Wait for next check
            await asyncio.sleep(settings.check_interval_minutes * 60)
    
    async def _check_all_users(self) -> None:
        """Check new matches for all users."""
        logger.info("🔍 Checking for new matches...")
        
        try:
            users = await storage.get_all_users()
            logger.info(f"👥 Monitoring {len(users)} users")
            
            for user in users:
                if not user.faceit_player_id:
                    continue
                
                try:
                    new_matches = await self.faceit_api.check_player_new_matches(
                        user.faceit_player_id,
                        user.last_checked_match_id
                    )
                    
                    logger.info(
                        f"🎮 Found {len(new_matches)} new matches for {user.faceit_nickname}"
                    )
                    
                    # Send notifications for new finished matches
                    for match in new_matches:
                        if match.status.upper() == "FINISHED":
                            logger.info(
                                f"📬 Sending notification for match {match.match_id} "
                                f"to user {user.user_id}"
                            )
                            await self.bot.send_match_notification(
                                user.user_id, 
                                match.match_id
                            )
                            
                            # Small delay between notifications
                            await asyncio.sleep(1)
                    
                    # Update last checked match if there were new matches
                    if new_matches:
                        await storage.update_last_checked_match(
                            user.user_id, 
                            new_matches[0].match_id
                        )
                
                except Exception as e:
                    logger.error(
                        f"❌ Error checking matches for user {user.user_id}: {e}"
                    )
                
                # Small delay between users
                await asyncio.sleep(0.5)
        
        except Exception as e:
            logger.error(f"❌ Error in check_all_users: {e}")
    
    async def check_now(self) -> None:
        """Manually trigger match check."""
        logger.info("🔍 Manual check for new matches triggered")
        await self._check_all_users()
    
    @property
    def status(self) -> dict:
        """Get monitor status."""
        return {
            "is_running": self.is_running,
            "interval_minutes": settings.check_interval_minutes
        }