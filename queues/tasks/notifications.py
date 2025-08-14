"""Background tasks for user notifications and messaging.

Handles sending notifications, alerts, reminders, and bulk messaging operations
in the background to ensure timely delivery without blocking the main bot thread.
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from enum import Enum

from rq import get_current_job
from rq.decorators import job

from faceit.api import FaceitAPI, FaceitAPIError
from faceit.models import FaceitMatch, PlayerMatchHistory
from utils.cache import CachedFaceitAPI
from utils.storage import storage
from utils.formatter import MessageFormatter
from config.settings import settings

logger = logging.getLogger(__name__)

# Initialize API instances
faceit_api = FaceitAPI()
cached_api = CachedFaceitAPI(faceit_api)


class NotificationType(Enum):
    """Types of notifications."""
    MATCH_COMPLETED = "match_completed"
    ELO_CHANGE = "elo_change"
    LEVEL_UP = "level_up"
    LEVEL_DOWN = "level_down"
    ACHIEVEMENT = "achievement"
    REMINDER = "reminder"
    ANNOUNCEMENT = "announcement"
    REPORT_READY = "report_ready"
    SUBSCRIPTION_EXPIRING = "subscription_expiring"
    SYSTEM_ALERT = "system_alert"


@dataclass
class NotificationResult:
    """Result of notification operation."""
    notification_type: NotificationType
    success: bool
    recipient_id: Optional[int] = None
    message_id: Optional[int] = None
    delivery_time_ms: Optional[int] = None
    error: Optional[str] = None
    retry_count: int = 0
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['notification_type'] = self.notification_type.value
        return result


def _run_async(coro):
    """Helper to run async code in sync job context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)


def _update_job_progress(current: int, total: int, operation: str = ""):
    """Update job progress metadata."""
    job = get_current_job()
    if job:
        progress = round((current / total) * 100, 1) if total > 0 else 0
        job.meta.update({
            'progress': {
                'current': current,
                'total': total,
                'percentage': progress,
                'operation': operation
            },
            'updated_at': datetime.now().isoformat()
        })
        job.save_meta()


@job('faceit_match_notification', timeout=300, result_ttl=1800)
def send_match_notification_task(
    user_id: int,
    match_id: str,
    notification_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Background task to send match completion notifications.
    
    Args:
        user_id: Telegram user ID to notify
        match_id: FACEIT match ID
        notification_data: Additional notification context
        
    Returns:
        Dict with notification sending results
    """
    logger.info(f"Starting match notification task for user {user_id}, match {match_id}")
    
    try:
        # Get user data
        user = _run_async(storage.get_user_data(user_id))
        if not user:
            return {
                "success": False,
                "error": "User not found",
                "user_id": user_id,
                "match_id": match_id
            }
        
        # Get match details
        match = _run_async(cached_api.get_match_details(match_id))
        if not match:
            return {
                "success": False,
                "error": "Match not found",
                "user_id": user_id,
                "match_id": match_id
            }
        
        # Get match statistics
        match_stats = _run_async(cached_api.get_match_stats(match_id))
        
        # Generate notification message
        notification_message = _generate_match_notification_message(
            user, match, match_stats, notification_data
        )
        
        if not notification_message:
            return {
                "success": False,
                "error": "Could not generate notification message",
                "user_id": user_id,
                "match_id": match_id
            }
        
        # Send notification
        result = _run_async(_send_telegram_notification(
            user_id, notification_message, NotificationType.MATCH_COMPLETED
        ))
        
        # Log notification
        if result.success:
            _run_async(storage.log_notification(
                user_id, NotificationType.MATCH_COMPLETED.value, 
                match_id, result.message_id
            ))
        
        return {
            "success": result.success,
            "user_id": user_id,
            "match_id": match_id,
            "message_id": result.message_id,
            "delivery_time_ms": result.delivery_time_ms,
            "error": result.error,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Match notification task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "user_id": user_id,
            "match_id": match_id,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_bulk_notifications', timeout=1800, result_ttl=3600)
def send_bulk_notifications_task(
    notification_type: str,
    recipients: List[int],
    message_template: str,
    personalization_data: Optional[Dict[int, Dict[str, Any]]] = None,
    batch_size: int = 10,
    delay_between_batches_ms: int = 1000
) -> Dict[str, Any]:
    """
    Background task to send bulk notifications to multiple users.
    
    Args:
        notification_type: Type of notification (enum value as string)
        recipients: List of Telegram user IDs
        message_template: Message template (can contain placeholders)
        personalization_data: Per-user data for message personalization
        batch_size: Number of notifications to send per batch
        delay_between_batches_ms: Delay between batches in milliseconds
        
    Returns:
        Dict with bulk notification results
    """
    logger.info(f"Starting bulk notification task for {len(recipients)} recipients")
    
    try:
        notification_enum = NotificationType(notification_type)
    except ValueError:
        return {
            "success": False,
            "error": f"Invalid notification type: {notification_type}",
            "timestamp": datetime.now().isoformat()
        }
    
    try:
        total_recipients = len(recipients)
        successful_sends = 0
        failed_sends = 0
        results = []
        
        # Process recipients in batches
        for i in range(0, total_recipients, batch_size):
            batch = recipients[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_recipients + batch_size - 1) // batch_size
            
            _update_job_progress(
                i, total_recipients, 
                f"Processing batch {batch_num}/{total_batches}"
            )
            
            # Process current batch
            batch_results = []
            for user_id in batch:
                try:
                    # Personalize message if data provided
                    personalized_message = message_template
                    if personalization_data and user_id in personalization_data:
                        user_data = personalization_data[user_id]
                        personalized_message = _personalize_message(message_template, user_data)
                    
                    # Send notification
                    result = _run_async(_send_telegram_notification(
                        user_id, personalized_message, notification_enum
                    ))
                    
                    batch_results.append(result)
                    
                    if result.success:
                        successful_sends += 1
                        # Log notification
                        _run_async(storage.log_notification(
                            user_id, notification_type, None, result.message_id
                        ))
                    else:
                        failed_sends += 1
                    
                    # Small delay between individual sends
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Error sending notification to user {user_id}: {e}")
                    batch_results.append(NotificationResult(
                        notification_type=notification_enum,
                        success=False,
                        recipient_id=user_id,
                        error=str(e)
                    ))
                    failed_sends += 1
            
            results.extend(batch_results)
            
            # Delay between batches
            if i + batch_size < total_recipients:
                await asyncio.sleep(delay_between_batches_ms / 1000)
        
        success_rate = round((successful_sends / total_recipients) * 100, 1)
        
        return {
            "success": True,
            "notification_type": notification_type,
            "total_recipients": total_recipients,
            "successful_sends": successful_sends,
            "failed_sends": failed_sends,
            "success_rate": success_rate,
            "batch_size": batch_size,
            "total_batches": (total_recipients + batch_size - 1) // batch_size,
            "results": [result.to_dict() for result in results],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Bulk notifications task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "notification_type": notification_type,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_scheduled_reminder', timeout=300, result_ttl=1800)
def schedule_reminder_task(
    user_id: int,
    reminder_type: str,
    reminder_data: Dict[str, Any],
    delay_hours: int = 24
) -> Dict[str, Any]:
    """
    Background task to schedule and send reminders to users.
    
    Args:
        user_id: Telegram user ID
        reminder_type: Type of reminder
        reminder_data: Data for reminder content
        delay_hours: Hours to wait before sending reminder
        
    Returns:
        Dict with reminder scheduling results
    """
    logger.info(f"Scheduling reminder for user {user_id} (delay: {delay_hours}h)")
    
    try:
        # Calculate reminder time
        reminder_time = datetime.now() + timedelta(hours=delay_hours)
        
        # Generate reminder message based on type
        reminder_message = _generate_reminder_message(reminder_type, reminder_data)
        
        if not reminder_message:
            return {
                "success": False,
                "error": f"Could not generate reminder message for type: {reminder_type}",
                "user_id": user_id
            }
        
        # Store reminder for later processing
        reminder_id = _run_async(storage.schedule_reminder(
            user_id, reminder_type, reminder_message, reminder_time, reminder_data
        ))
        
        return {
            "success": True,
            "user_id": user_id,
            "reminder_type": reminder_type,
            "reminder_id": reminder_id,
            "scheduled_time": reminder_time.isoformat(),
            "delay_hours": delay_hours,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Reminder scheduling task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "user_id": user_id,
            "reminder_type": reminder_type,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_analytics_report_notification', timeout=600, result_ttl=3600)
def send_analytics_report_task(
    user_id: int,
    report_data: Dict[str, Any],
    report_type: str = "weekly",
    include_attachments: bool = False
) -> Dict[str, Any]:
    """
    Background task to send analytics reports to users.
    
    Args:
        user_id: Telegram user ID
        report_data: Generated report data
        report_type: Type of report (weekly, monthly, custom)
        include_attachments: Whether to include visual attachments
        
    Returns:
        Dict with report notification results
    """
    logger.info(f"Sending analytics report to user {user_id} (type: {report_type})")
    
    try:
        # Get user data
        user = _run_async(storage.get_user_data(user_id))
        if not user:
            return {
                "success": False,
                "error": "User not found",
                "user_id": user_id
            }
        
        # Generate report message
        report_message = _generate_analytics_report_message(
            user, report_data, report_type
        )
        
        if not report_message:
            return {
                "success": False,
                "error": "Could not generate report message",
                "user_id": user_id
            }
        
        # Send report notification
        result = _run_async(_send_telegram_notification(
            user_id, report_message, NotificationType.REPORT_READY
        ))
        
        # Send attachments if requested
        attachment_results = []
        if include_attachments and result.success:
            attachments = _generate_report_attachments(report_data, report_type)
            for attachment in attachments:
                attachment_result = _run_async(_send_telegram_attachment(
                    user_id, attachment
                ))
                attachment_results.append(attachment_result.to_dict())
        
        # Log notification
        if result.success:
            _run_async(storage.log_notification(
                user_id, NotificationType.REPORT_READY.value, 
                f"report_{report_type}", result.message_id
            ))
        
        return {
            "success": result.success,
            "user_id": user_id,
            "report_type": report_type,
            "message_id": result.message_id,
            "attachments_sent": len(attachment_results),
            "attachment_results": attachment_results,
            "delivery_time_ms": result.delivery_time_ms,
            "error": result.error,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Analytics report notification task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "user_id": user_id,
            "report_type": report_type,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_broadcast_announcement', timeout=3600, result_ttl=3600)
def broadcast_announcement_task(
    announcement: str,
    target_users: str = "all",
    user_filters: Optional[Dict[str, Any]] = None,
    scheduling_options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Background task to broadcast announcements to users.
    
    Args:
        announcement: Announcement message
        target_users: Target user group ("all", "premium", "active", "filtered")
        user_filters: Additional user filtering criteria
        scheduling_options: Options for scheduling broadcast
        
    Returns:
        Dict with broadcast results
    """
    logger.info(f"Starting announcement broadcast (target: {target_users})")
    
    try:
        # Get target user list
        target_user_ids = _run_async(_get_broadcast_targets(target_users, user_filters))
        
        if not target_user_ids:
            return {
                "success": True,
                "message": "No users match the target criteria",
                "target_users": target_users,
                "announcement_preview": announcement[:100] + "..." if len(announcement) > 100 else announcement,
                "timestamp": datetime.now().isoformat()
            }
        
        logger.info(f"Broadcasting to {len(target_user_ids)} users")
        
        # Check for scheduling
        if scheduling_options and scheduling_options.get("scheduled_time"):
            # Schedule for later
            scheduled_time = datetime.fromisoformat(scheduling_options["scheduled_time"])
            
            # Store scheduled broadcast
            broadcast_id = _run_async(storage.schedule_broadcast(
                announcement, target_user_ids, scheduled_time, user_filters
            ))
            
            return {
                "success": True,
                "scheduled": True,
                "broadcast_id": broadcast_id,
                "target_user_count": len(target_user_ids),
                "scheduled_time": scheduled_time.isoformat(),
                "announcement_preview": announcement[:100] + "..." if len(announcement) > 100 else announcement,
                "timestamp": datetime.now().isoformat()
            }
        
        # Send immediate broadcast
        broadcast_result = _run_async(_execute_broadcast(
            announcement, target_user_ids, scheduling_options
        ))
        
        return {
            "success": True,
            "scheduled": False,
            "target_users": target_users,
            "target_user_count": len(target_user_ids),
            "successful_sends": broadcast_result.get("successful_sends", 0),
            "failed_sends": broadcast_result.get("failed_sends", 0),
            "success_rate": broadcast_result.get("success_rate", 0),
            "announcement_preview": announcement[:100] + "..." if len(announcement) > 100 else announcement,
            "broadcast_duration_ms": broadcast_result.get("duration_ms", 0),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Announcement broadcast task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "target_users": target_users,
            "timestamp": datetime.now().isoformat()
        }


# Helper functions

def _generate_match_notification_message(
    user, 
    match: FaceitMatch, 
    match_stats, 
    notification_data: Optional[Dict[str, Any]]
) -> Optional[str]:
    """Generate match completion notification message."""
    try:
        if not match.results:
            return None
        
        # Determine if user's team won
        user_faction = None
        user_team_name = None
        
        for team_name, team_data in match.teams.items():
            for player in team_data.players:
                if player.player_id == user.faceit_player_id:
                    user_faction = team_data.faction_id
                    user_team_name = team_name
                    break
        
        if not user_faction:
            return None
        
        is_win = user_faction == match.results.winner
        result_emoji = "🎉" if is_win else "😔"
        result_text = "VICTORY" if is_win else "DEFEAT"
        
        # Get user stats from match
        user_stats = None
        if match_stats:
            user_stats = MessageFormatter._get_player_stats_from_match(match_stats, user.faceit_player_id)
        
        # Build message
        message_parts = [
            f"{result_emoji} <b>{result_text}!</b>",
            f"",
            f"🏆 <b>{match.competition_name}</b>",
            f"⚔️ <b>{user_team_name}</b> vs opponents"
        ]
        
        # Add score if available
        if match.results and match.results.score:
            faction1_score = match.results.score.get('faction1', 0)
            faction2_score = match.results.score.get('faction2', 0)
            message_parts.append(f"📊 Score: {faction1_score} - {faction2_score}")
        
        # Add user performance if available
        if user_stats:
            stats_dict = user_stats.player_stats
            kills = stats_dict.get('Kills', '0')
            deaths = stats_dict.get('Deaths', '0')
            assists = stats_dict.get('Assists', '0')
            
            kd_ratio = round(int(kills) / max(int(deaths), 1), 2)
            
            message_parts.extend([
                "",
                f"📈 <b>Your Performance:</b>",
                f"🔫 K/D/A: {kills}/{deaths}/{assists} ({kd_ratio})",
                f"💥 ADR: {stats_dict.get('ADR', '0')}"
            ])
            
            if 'Headshots' in stats_dict:
                hs_percentage = round((int(stats_dict.get('Headshots', '0')) / max(int(kills), 1)) * 100, 1)
                message_parts.append(f"🎯 HS%: {hs_percentage}%")
        
        # Add ELO change if available
        if notification_data and 'elo_change' in notification_data:
            elo_change = notification_data['elo_change']
            if elo_change != 0:
                elo_emoji = "📈" if elo_change > 0 else "📉"
                sign = "+" if elo_change > 0 else ""
                message_parts.append(f"")
                message_parts.append(f"{elo_emoji} ELO: {sign}{elo_change}")
        
        message_parts.append(f"")
        message_parts.append(f"🚀 Great game! Keep it up!")
        
        return "\n".join(message_parts)
        
    except Exception as e:
        logger.error(f"Error generating match notification message: {e}")
        return None


def _generate_reminder_message(reminder_type: str, reminder_data: Dict[str, Any]) -> Optional[str]:
    """Generate reminder message based on type."""
    try:
        if reminder_type == "subscription_expiring":
            days_left = reminder_data.get('days_left', 0)
            subscription_type = reminder_data.get('subscription_type', 'Premium')
            
            return f"""⚠️ <b>Subscription Expiring</b>

Your {subscription_type} subscription expires in {days_left} days.

💡 Renew now to continue enjoying:
• Unlimited match analysis
• Priority support
• Advanced statistics

Use /subscription to renew!"""
        
        elif reminder_type == "inactivity":
            days_inactive = reminder_data.get('days_inactive', 7)
            
            return f"""👋 <b>We miss you!</b>

You haven't used FACEIT Bot in {days_inactive} days.

🎮 Check out these features:
• /analyze - Analyze your matches
• /profile - View your stats
• /monitor - Track your progress

Jump back in and dominate! 💪"""
        
        elif reminder_type == "feature_update":
            feature_name = reminder_data.get('feature_name', 'New Feature')
            
            return f"""🆕 <b>{feature_name} Available!</b>

We've added something new you might love.

Try it out with the latest commands and let us know what you think!"""
        
        return None
        
    except Exception as e:
        logger.error(f"Error generating reminder message: {e}")
        return None


def _generate_analytics_report_message(
    user, 
    report_data: Dict[str, Any], 
    report_type: str
) -> Optional[str]:
    """Generate analytics report notification message."""
    try:
        period_name = report_type.capitalize()
        
        message_parts = [
            f"📊 <b>Your {period_name} Report</b>",
            f"",
            f"👋 Hi {user.faceit_nickname or 'Player'}!"
        ]
        
        # Add key statistics
        if 'summary' in report_data:
            summary = report_data['summary']
            message_parts.extend([
                "",
                f"🎮 <b>Performance Summary:</b>",
                f"• Matches played: {summary.get('matches_played', 0)}",
                f"• Win rate: {summary.get('winrate', 0)}%",
                f"• Average K/D: {summary.get('avg_kd', 0)}",
                f"• HLTV Rating: {summary.get('hltv_rating', 0)}"
            ])
        
        # Add improvements/declines
        if 'trends' in report_data:
            trends = report_data['trends']
            if trends.get('improving_areas'):
                message_parts.append("")
                message_parts.append("📈 <b>Improvements:</b>")
                for area in trends['improving_areas'][:3]:
                    message_parts.append(f"• {area}")
        
        # Add recommendations
        if 'recommendations' in report_data:
            recommendations = report_data['recommendations'][:2]
            if recommendations:
                message_parts.append("")
                message_parts.append("💡 <b>Recommendations:</b>")
                for rec in recommendations:
                    message_parts.append(f"• {rec}")
        
        message_parts.extend([
            "",
            "📱 Use /analytics to see your detailed statistics!",
            "",
            "🚀 Keep grinding and improving!"
        ])
        
        return "\n".join(message_parts)
        
    except Exception as e:
        logger.error(f"Error generating analytics report message: {e}")
        return None


def _personalize_message(template: str, user_data: Dict[str, Any]) -> str:
    """Personalize message template with user data."""
    try:
        personalized = template
        
        # Replace common placeholders
        replacements = {
            "{nickname}": user_data.get('nickname', 'Player'),
            "{first_name}": user_data.get('first_name', 'there'),
            "{elo}": str(user_data.get('elo', 0)),
            "{level}": str(user_data.get('level', 0)),
            "{matches_played}": str(user_data.get('matches_played', 0)),
            "{winrate}": str(user_data.get('winrate', 0))
        }
        
        for placeholder, value in replacements.items():
            personalized = personalized.replace(placeholder, value)
        
        return personalized
        
    except Exception as e:
        logger.error(f"Error personalizing message: {e}")
        return template


def _generate_report_attachments(report_data: Dict[str, Any], report_type: str) -> List[Dict[str, Any]]:
    """Generate visual attachments for reports."""
    # This would generate charts, graphs, etc.
    # For now, return empty list as placeholder
    return []


async def _send_telegram_notification(
    user_id: int, 
    message: str, 
    notification_type: NotificationType
) -> NotificationResult:
    """Send notification via Telegram bot."""
    start_time = datetime.now()
    
    try:
        # Import bot instance (avoid circular imports)
        from bot.bot import bot
        
        # Send message
        sent_message = await bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        delivery_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return NotificationResult(
            notification_type=notification_type,
            success=True,
            recipient_id=user_id,
            message_id=sent_message.message_id,
            delivery_time_ms=delivery_time
        )
        
    except Exception as e:
        delivery_time = int((datetime.now() - start_time).total_seconds() * 1000)
        logger.error(f"Failed to send notification to user {user_id}: {e}")
        
        return NotificationResult(
            notification_type=notification_type,
            success=False,
            recipient_id=user_id,
            delivery_time_ms=delivery_time,
            error=str(e)
        )


async def _send_telegram_attachment(user_id: int, attachment: Dict[str, Any]) -> NotificationResult:
    """Send attachment via Telegram bot."""
    try:
        # Import bot instance
        from bot.bot import bot
        
        # Send attachment based on type
        attachment_type = attachment.get('type')
        
        if attachment_type == 'photo':
            sent_message = await bot.send_photo(
                chat_id=user_id,
                photo=attachment['data'],
                caption=attachment.get('caption')
            )
        elif attachment_type == 'document':
            sent_message = await bot.send_document(
                chat_id=user_id,
                document=attachment['data'],
                caption=attachment.get('caption')
            )
        else:
            raise ValueError(f"Unsupported attachment type: {attachment_type}")
        
        return NotificationResult(
            notification_type=NotificationType.REPORT_READY,
            success=True,
            recipient_id=user_id,
            message_id=sent_message.message_id
        )
        
    except Exception as e:
        logger.error(f"Failed to send attachment to user {user_id}: {e}")
        return NotificationResult(
            notification_type=NotificationType.REPORT_READY,
            success=False,
            recipient_id=user_id,
            error=str(e)
        )


async def _get_broadcast_targets(
    target_users: str, 
    user_filters: Optional[Dict[str, Any]]
) -> List[int]:
    """Get list of user IDs for broadcast targeting."""
    try:
        all_users = await storage.get_all_users()
        
        if target_users == "all":
            return [user.user_id for user in all_users]
        
        elif target_users == "premium":
            return [
                user.user_id for user in all_users 
                if hasattr(user, 'subscription') and 
                user.subscription and 
                user.subscription.tier in ["PREMIUM", "PRO"]
            ]
        
        elif target_users == "active":
            cutoff_date = datetime.now() - timedelta(days=7)
            return [
                user.user_id for user in all_users
                if hasattr(user, 'last_activity') and
                user.last_activity and
                user.last_activity > cutoff_date
            ]
        
        elif target_users == "filtered" and user_filters:
            # Apply custom filters
            filtered_users = all_users
            
            if 'min_level' in user_filters:
                min_level = user_filters['min_level']
                filtered_users = [
                    user for user in filtered_users
                    if hasattr(user, 'last_known_level') and
                    user.last_known_level and
                    user.last_known_level >= min_level
                ]
            
            if 'country' in user_filters:
                target_country = user_filters['country'].upper()
                filtered_users = [
                    user for user in filtered_users
                    if hasattr(user, 'country') and
                    user.country and
                    user.country.upper() == target_country
                ]
            
            return [user.user_id for user in filtered_users]
        
        return []
        
    except Exception as e:
        logger.error(f"Error getting broadcast targets: {e}")
        return []


async def _execute_broadcast(
    announcement: str, 
    target_user_ids: List[int], 
    options: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Execute immediate broadcast to target users."""
    start_time = datetime.now()
    
    try:
        batch_size = options.get('batch_size', 20) if options else 20
        delay_ms = options.get('delay_between_batches_ms', 1000) if options else 1000
        
        successful_sends = 0
        failed_sends = 0
        
        # Send in batches
        for i in range(0, len(target_user_ids), batch_size):
            batch = target_user_ids[i:i + batch_size]
            
            # Send to current batch
            for user_id in batch:
                try:
                    result = await _send_telegram_notification(
                        user_id, announcement, NotificationType.ANNOUNCEMENT
                    )
                    
                    if result.success:
                        successful_sends += 1
                        # Log broadcast
                        await storage.log_notification(
                            user_id, NotificationType.ANNOUNCEMENT.value,
                            "broadcast", result.message_id
                        )
                    else:
                        failed_sends += 1
                    
                    # Small delay between individual sends
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Error sending broadcast to user {user_id}: {e}")
                    failed_sends += 1
            
            # Delay between batches
            if i + batch_size < len(target_user_ids):
                await asyncio.sleep(delay_ms / 1000)
        
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        success_rate = round((successful_sends / len(target_user_ids)) * 100, 1)
        
        return {
            "successful_sends": successful_sends,
            "failed_sends": failed_sends,
            "success_rate": success_rate,
            "duration_ms": duration_ms
        }
        
    except Exception as e:
        logger.error(f"Error executing broadcast: {e}")
        return {
            "successful_sends": 0,
            "failed_sends": len(target_user_ids),
            "success_rate": 0,
            "error": str(e)
        }