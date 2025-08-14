"""Background tasks for player monitoring and statistics updates.

Handles regular player statistics updates, ELO tracking, match monitoring,
and performance analytics in the background to keep data fresh and reduce
API calls during user interactions.
"""

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

from rq import get_current_job
from rq.decorators import job

from faceit.api import FaceitAPI, FaceitAPIError
from faceit.models import FaceitPlayer, PlayerMatchHistory
from utils.cache import CachedFaceitAPI
from utils.storage import storage
from utils.formatter import MessageFormatter
from config.settings import settings

logger = logging.getLogger(__name__)

# Initialize API instances
faceit_api = FaceitAPI()
cached_api = CachedFaceitAPI(faceit_api)


@dataclass
class PlayerMonitoringResult:
    """Result of player monitoring operation."""
    player_id: str
    nickname: str
    success: bool
    updates_applied: int = 0
    new_matches_found: int = 0
    elo_change: int = 0
    error: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


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


@job('faceit_player_monitoring', timeout=3600, result_ttl=1800)
def monitor_player_matches_task(
    player_ids: Optional[List[str]] = None,
    check_period_hours: int = 24,
    send_notifications: bool = True
) -> Dict[str, Any]:
    """
    Background task to monitor players for new matches and updates.
    
    This task checks for new matches for monitored players and can send
    notifications when new completed matches are found.
    
    Args:
        player_ids: Specific player IDs to monitor (None for all monitored players)
        check_period_hours: How many hours back to check for new matches
        send_notifications: Whether to send notifications for new matches
        
    Returns:
        Dict with monitoring results
    """
    job = get_current_job()
    job_id = job.id if job else "unknown"
    logger.info(f"Starting player monitoring task (ID: {job_id})")
    
    try:
        # Get list of players to monitor
        if player_ids:
            # Monitor specific players
            users_to_monitor = []
            for player_id in player_ids:
                user_data = _run_async(storage.get_user_by_faceit_id(player_id))
                if user_data:
                    users_to_monitor.append(user_data)
        else:
            # Monitor all users with linked FACEIT accounts
            all_users = _run_async(storage.get_all_users())
            users_to_monitor = [user for user in all_users if user.faceit_player_id]
        
        if not users_to_monitor:
            return {
                "success": True,
                "message": "No players to monitor",
                "players_monitored": 0,
                "timestamp": datetime.now().isoformat()
            }
        
        logger.info(f"Monitoring {len(users_to_monitor)} players")
        
        # Process players in batches to manage API rate limits
        batch_size = 10
        results = []
        notifications_sent = 0
        total_new_matches = 0
        
        for i in range(0, len(users_to_monitor), batch_size):
            batch = users_to_monitor[i:i + batch_size]
            _update_job_progress(i, len(users_to_monitor), f"Processing batch {i//batch_size + 1}")
            
            # Process batch
            batch_results = []
            for user in batch:
                try:
                    result = _run_async(_monitor_single_player(
                        user, check_period_hours, send_notifications
                    ))
                    batch_results.append(result)
                    
                    if result.success:
                        total_new_matches += result.new_matches_found
                        if result.new_matches_found > 0 and send_notifications:
                            notifications_sent += 1
                    
                except Exception as e:
                    logger.error(f"Error monitoring player {user.faceit_player_id}: {e}")
                    batch_results.append(PlayerMonitoringResult(
                        player_id=user.faceit_player_id,
                        nickname=user.faceit_nickname or "Unknown",
                        success=False,
                        error=str(e)
                    ))
            
            results.extend(batch_results)
            
            # Rate limiting between batches
            if i + batch_size < len(users_to_monitor):
                await asyncio.sleep(2)
        
        # Compile final results
        successful_monitoring = len([r for r in results if r.success])
        failed_monitoring = len(results) - successful_monitoring
        
        final_result = {
            "success": True,
            "players_monitored": len(users_to_monitor),
            "successful_monitoring": successful_monitoring,
            "failed_monitoring": failed_monitoring,
            "total_new_matches_found": total_new_matches,
            "notifications_sent": notifications_sent,
            "check_period_hours": check_period_hours,
            "results": [
                {
                    "player_id": r.player_id,
                    "nickname": r.nickname,
                    "success": r.success,
                    "new_matches": r.new_matches_found,
                    "elo_change": r.elo_change,
                    "error": r.error
                } for r in results
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"Player monitoring completed: {successful_monitoring}/{len(users_to_monitor)} successful")
        return final_result
        
    except Exception as e:
        logger.error(f"Player monitoring task failed: {e}")
        return {
            "success": False,
            "error": f"Monitoring task failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_player_stats_update', timeout=1800, result_ttl=3600)
def update_player_statistics_task(
    player_ids: List[str],
    force_full_update: bool = False,
    update_match_history: bool = True
) -> Dict[str, Any]:
    """
    Background task to update player statistics and cache fresh data.
    
    Args:
        player_ids: List of FACEIT player IDs to update
        force_full_update: Force complete statistics refresh
        update_match_history: Whether to update match history
        
    Returns:
        Dict with update results
    """
    logger.info(f"Starting statistics update for {len(player_ids)} players")
    
    try:
        results = []
        successful_updates = 0
        cache_updates = 0
        
        for i, player_id in enumerate(player_ids):
            _update_job_progress(i, len(player_ids), f"Updating player {i+1}/{len(player_ids)}")
            
            try:
                result = _run_async(_update_single_player_stats(
                    player_id, force_full_update, update_match_history
                ))
                
                results.append(result)
                
                if result.success:
                    successful_updates += 1
                    cache_updates += result.updates_applied
                
                # Rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error updating player {player_id}: {e}")
                results.append(PlayerMonitoringResult(
                    player_id=player_id,
                    nickname="Unknown",
                    success=False,
                    error=str(e)
                ))
        
        return {
            "success": True,
            "total_players": len(player_ids),
            "successful_updates": successful_updates,
            "failed_updates": len(player_ids) - successful_updates,
            "cache_updates_applied": cache_updates,
            "force_full_update": force_full_update,
            "results": [
                {
                    "player_id": r.player_id,
                    "nickname": r.nickname,
                    "success": r.success,
                    "updates_applied": r.updates_applied,
                    "error": r.error
                } for r in results
            ],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Player statistics update task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_batch_player_update', timeout=7200, result_ttl=7200)  # 2 hours
def batch_update_players_task(
    batch_size: int = 50,
    update_interval_hours: int = 6,
    priority_players: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Background task for batch updating all monitored players.
    
    This task runs periodically to keep all player data fresh, prioritizing
    active users and recently active players.
    
    Args:
        batch_size: Number of players to process in each batch
        update_interval_hours: Only update players not updated in this interval
        priority_players: Player IDs to prioritize for updates
        
    Returns:
        Dict with batch update results
    """
    logger.info(f"Starting batch player update (batch size: {batch_size})")
    
    try:
        # Get all users with FACEIT accounts
        all_users = _run_async(storage.get_all_users())
        monitored_users = [user for user in all_users if user.faceit_player_id]
        
        if not monitored_users:
            return {
                "success": True,
                "message": "No players to update",
                "timestamp": datetime.now().isoformat()
            }
        
        # Filter users that need updates
        cutoff_time = datetime.now() - timedelta(hours=update_interval_hours)
        users_to_update = []
        
        for user in monitored_users:
            # Check if user needs update (hasn't been updated recently)
            needs_update = True
            
            if hasattr(user, 'last_stats_update') and user.last_stats_update:
                if user.last_stats_update > cutoff_time:
                    needs_update = False
            
            # Prioritize priority players
            if priority_players and user.faceit_player_id in priority_players:
                needs_update = True
            
            if needs_update:
                users_to_update.append(user)
        
        logger.info(f"Found {len(users_to_update)} players needing updates")
        
        if not users_to_update:
            return {
                "success": True,
                "message": "All players are up to date",
                "total_monitored": len(monitored_users),
                "timestamp": datetime.now().isoformat()
            }
        
        # Process in batches
        total_batches = (len(users_to_update) + batch_size - 1) // batch_size
        batch_results = []
        total_successful = 0
        total_failed = 0
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(users_to_update))
            batch_users = users_to_update[start_idx:end_idx]
            
            _update_job_progress(
                batch_num, total_batches, 
                f"Processing batch {batch_num + 1}/{total_batches}"
            )
            
            logger.info(f"Processing batch {batch_num + 1}/{total_batches} ({len(batch_users)} players)")
            
            # Update players in current batch
            batch_player_ids = [user.faceit_player_id for user in batch_users]
            batch_result = _run_async(_update_player_batch(batch_player_ids))
            
            batch_results.append({
                "batch_number": batch_num + 1,
                "players_in_batch": len(batch_users),
                "successful": batch_result.get("successful_updates", 0),
                "failed": batch_result.get("failed_updates", 0),
                "timestamp": datetime.now().isoformat()
            })
            
            total_successful += batch_result.get("successful_updates", 0)
            total_failed += batch_result.get("failed_updates", 0)
            
            # Delay between batches to respect rate limits
            if batch_num < total_batches - 1:
                await asyncio.sleep(10)
        
        # Update completion timestamps
        for user in users_to_update[:total_successful]:
            try:
                _run_async(storage.update_user_stats_timestamp(user.user_id, datetime.now()))
            except Exception as e:
                logger.warning(f"Failed to update timestamp for user {user.user_id}: {e}")
        
        return {
            "success": True,
            "total_monitored_players": len(monitored_users),
            "players_needing_update": len(users_to_update),
            "total_batches_processed": total_batches,
            "total_successful_updates": total_successful,
            "total_failed_updates": total_failed,
            "success_rate": round((total_successful / len(users_to_update)) * 100, 1),
            "batch_results": batch_results,
            "update_interval_hours": update_interval_hours,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Batch player update task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_elo_tracking', timeout=1800, result_ttl=3600)
def check_elo_changes_task(
    player_ids: Optional[List[str]] = None,
    notification_threshold: int = 50,
    track_all_changes: bool = True
) -> Dict[str, Any]:
    """
    Background task to check for significant ELO changes and track progression.
    
    Args:
        player_ids: Specific players to check (None for all monitored)
        notification_threshold: ELO change threshold for notifications
        track_all_changes: Whether to track all ELO changes or only significant ones
        
    Returns:
        Dict with ELO change results
    """
    logger.info("Starting ELO change tracking task")
    
    try:
        # Get players to monitor
        if player_ids:
            users_to_check = []
            for player_id in player_ids:
                user_data = _run_async(storage.get_user_by_faceit_id(player_id))
                if user_data:
                    users_to_check.append(user_data)
        else:
            all_users = _run_async(storage.get_all_users())
            users_to_check = [user for user in all_users if user.faceit_player_id]
        
        if not users_to_check:
            return {
                "success": True,
                "message": "No players to check for ELO changes",
                "timestamp": datetime.now().isoformat()
            }
        
        elo_changes = []
        significant_changes = 0
        total_changes_tracked = 0
        
        for i, user in enumerate(users_to_check):
            _update_job_progress(i, len(users_to_check), f"Checking ELO for {user.faceit_nickname}")
            
            try:
                # Get current player data
                current_player = _run_async(cached_api.get_player_by_id(user.faceit_player_id))
                if not current_player or 'cs2' not in current_player.games:
                    continue
                
                current_elo = current_player.games['cs2'].faceit_elo
                current_level = current_player.games['cs2'].skill_level
                
                # Get stored ELO data
                stored_elo = getattr(user, 'last_known_elo', None)
                stored_level = getattr(user, 'last_known_level', None)
                
                if stored_elo is not None:
                    elo_change = current_elo - stored_elo
                    level_change = current_level - (stored_level or 0)
                    
                    if abs(elo_change) > 0 or level_change != 0:
                        change_data = {
                            "player_id": user.faceit_player_id,
                            "nickname": user.faceit_nickname,
                            "previous_elo": stored_elo,
                            "current_elo": current_elo,
                            "elo_change": elo_change,
                            "previous_level": stored_level,
                            "current_level": current_level,
                            "level_change": level_change,
                            "is_significant": abs(elo_change) >= notification_threshold,
                            "timestamp": datetime.now().isoformat()
                        }
                        
                        elo_changes.append(change_data)
                        total_changes_tracked += 1
                        
                        if abs(elo_change) >= notification_threshold:
                            significant_changes += 1
                
                # Update stored ELO data
                _run_async(storage.update_user_elo_data(
                    user.user_id, current_elo, current_level
                ))
                
                # Rate limiting
                await asyncio.sleep(0.3)
                
            except Exception as e:
                logger.error(f"Error checking ELO for player {user.faceit_player_id}: {e}")
                continue
        
        return {
            "success": True,
            "players_checked": len(users_to_check),
            "total_changes_tracked": total_changes_tracked,
            "significant_changes": significant_changes,
            "notification_threshold": notification_threshold,
            "elo_changes": elo_changes if track_all_changes else [
                change for change in elo_changes if change["is_significant"]
            ],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"ELO tracking task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_activity_tracking', timeout=1800, result_ttl=3600)
def track_player_activity_task(
    activity_period_days: int = 7,
    inactivity_threshold_days: int = 14
) -> Dict[str, Any]:
    """
    Background task to track player activity and identify inactive users.
    
    Args:
        activity_period_days: Period to analyze for activity
        inactivity_threshold_days: Days without matches to consider inactive
        
    Returns:
        Dict with activity tracking results
    """
    logger.info(f"Starting player activity tracking (period: {activity_period_days} days)")
    
    try:
        all_users = _run_async(storage.get_all_users())
        monitored_users = [user for user in all_users if user.faceit_player_id]
        
        if not monitored_users:
            return {
                "success": True,
                "message": "No players to track",
                "timestamp": datetime.now().isoformat()
            }
        
        active_players = []
        inactive_players = []
        activity_stats = {
            "very_active": 0,    # 5+ matches per week
            "active": 0,         # 2-4 matches per week
            "low_active": 0,     # 1 match per week
            "inactive": 0        # No recent matches
        }
        
        cutoff_date = datetime.now() - timedelta(days=activity_period_days)
        inactivity_cutoff = datetime.now() - timedelta(days=inactivity_threshold_days)
        
        for i, user in enumerate(monitored_users):
            _update_job_progress(i, len(monitored_users), f"Tracking activity for {user.faceit_nickname}")
            
            try:
                # Get recent matches
                recent_matches = _run_async(cached_api.get_player_matches(
                    user.faceit_player_id, limit=20
                ))
                
                # Filter matches within activity period
                activity_matches = []
                latest_match_date = None
                
                for match in recent_matches:
                    try:
                        if hasattr(match, 'finished_at') and match.finished_at:
                            match_date = datetime.fromisoformat(match.finished_at.replace('Z', '+00:00'))
                            
                            if not latest_match_date or match_date > latest_match_date:
                                latest_match_date = match_date
                            
                            if match_date >= cutoff_date:
                                activity_matches.append(match)
                    except (ValueError, AttributeError):
                        continue
                
                # Classify activity level
                matches_count = len(activity_matches)
                is_inactive = latest_match_date and latest_match_date < inactivity_cutoff
                
                activity_data = {
                    "player_id": user.faceit_player_id,
                    "nickname": user.faceit_nickname,
                    "matches_in_period": matches_count,
                    "latest_match_date": latest_match_date.isoformat() if latest_match_date else None,
                    "days_since_last_match": (datetime.now() - latest_match_date).days if latest_match_date else None,
                    "is_inactive": is_inactive
                }
                
                if is_inactive:
                    activity_data["activity_level"] = "inactive"
                    activity_stats["inactive"] += 1
                    inactive_players.append(activity_data)
                elif matches_count >= 5:
                    activity_data["activity_level"] = "very_active"
                    activity_stats["very_active"] += 1
                    active_players.append(activity_data)
                elif matches_count >= 2:
                    activity_data["activity_level"] = "active"
                    activity_stats["active"] += 1
                    active_players.append(activity_data)
                elif matches_count >= 1:
                    activity_data["activity_level"] = "low_active"
                    activity_stats["low_active"] += 1
                    active_players.append(activity_data)
                else:
                    activity_data["activity_level"] = "inactive"
                    activity_stats["inactive"] += 1
                    inactive_players.append(activity_data)
                
                # Rate limiting
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error tracking activity for player {user.faceit_player_id}: {e}")
                continue
        
        return {
            "success": True,
            "total_players": len(monitored_users),
            "activity_period_days": activity_period_days,
            "inactivity_threshold_days": inactivity_threshold_days,
            "activity_statistics": activity_stats,
            "active_players": active_players,
            "inactive_players": inactive_players,
            "activity_rate": round((len(active_players) / len(monitored_users)) * 100, 1),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Activity tracking task failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# Helper functions

async def _monitor_single_player(
    user, 
    check_period_hours: int, 
    send_notifications: bool
) -> PlayerMonitoringResult:
    """Monitor a single player for new matches."""
    try:
        # Get recent matches
        recent_matches = await faceit_api.check_player_new_matches(
            user.faceit_player_id,
            user.last_checked_match_id
        )
        
        new_matches_count = len(recent_matches)
        
        # Update last checked match if there are new matches
        if recent_matches:
            await storage.update_last_checked_match(
                user.user_id,
                recent_matches[0].match_id
            )
        
        # Check for ELO changes
        current_player = await cached_api.get_player_by_id(user.faceit_player_id)
        elo_change = 0
        
        if current_player and 'cs2' in current_player.games:
            current_elo = current_player.games['cs2'].faceit_elo
            stored_elo = getattr(user, 'last_known_elo', current_elo)
            elo_change = current_elo - stored_elo
            
            # Update stored ELO
            if elo_change != 0:
                await storage.update_user_elo_data(user.user_id, current_elo, current_player.games['cs2'].skill_level)
        
        return PlayerMonitoringResult(
            player_id=user.faceit_player_id,
            nickname=user.faceit_nickname or current_player.nickname if current_player else "Unknown",
            success=True,
            new_matches_found=new_matches_count,
            elo_change=elo_change,
            updates_applied=1 if new_matches_count > 0 or elo_change != 0 else 0
        )
        
    except Exception as e:
        logger.error(f"Error monitoring player {user.faceit_player_id}: {e}")
        return PlayerMonitoringResult(
            player_id=user.faceit_player_id,
            nickname=user.faceit_nickname or "Unknown",
            success=False,
            error=str(e)
        )


async def _update_single_player_stats(
    player_id: str, 
    force_full_update: bool, 
    update_match_history: bool
) -> PlayerMonitoringResult:
    """Update statistics for a single player."""
    try:
        updates_applied = 0
        
        # Get fresh player data
        player = await faceit_api.get_player_by_id(player_id)
        if not player:
            return PlayerMonitoringResult(
                player_id=player_id,
                nickname="Unknown",
                success=False,
                error="Player not found"
            )
        
        # Update player cache
        await cached_api.get_player_by_id(player_id)  # This will refresh the cache
        updates_applied += 1
        
        # Update match history if requested
        if update_match_history:
            await cached_api.get_player_matches(player_id, limit=50)
            updates_applied += 1
            
            # Get match statistics for recent matches
            if force_full_update:
                await cached_api.get_matches_with_stats(player_id, limit=30)
                updates_applied += 1
        
        return PlayerMonitoringResult(
            player_id=player_id,
            nickname=player.nickname,
            success=True,
            updates_applied=updates_applied
        )
        
    except Exception as e:
        logger.error(f"Error updating player stats {player_id}: {e}")
        return PlayerMonitoringResult(
            player_id=player_id,
            nickname="Unknown",
            success=False,
            error=str(e)
        )


async def _update_player_batch(player_ids: List[str]) -> Dict[str, Any]:
    """Update a batch of players with rate limiting."""
    successful_updates = 0
    failed_updates = 0
    
    # Use semaphore to limit concurrent updates
    semaphore = asyncio.Semaphore(5)
    
    async def update_with_limit(player_id):
        async with semaphore:
            try:
                result = await _update_single_player_stats(player_id, False, True)
                return result.success
            except Exception as e:
                logger.error(f"Batch update failed for {player_id}: {e}")
                return False
    
    # Create tasks for all players
    tasks = [update_with_limit(player_id) for player_id in player_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Count results
    for result in results:
        if isinstance(result, Exception):
            failed_updates += 1
        elif result:
            successful_updates += 1
        else:
            failed_updates += 1
    
    return {
        "successful_updates": successful_updates,
        "failed_updates": failed_updates
    }