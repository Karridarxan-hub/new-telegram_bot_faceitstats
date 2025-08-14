"""Background job definitions for FACEIT operations."""

import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import json

from rq import get_current_job
from rq.decorators import job

from faceit.api import FaceitAPI, FaceitAPIError
from utils.match_analyzer import MatchAnalyzer, format_match_analysis
from utils.formatter import MessageFormatter
from utils.storage import storage
from utils.cache import CachedFaceitAPI
from config.settings import settings

logger = logging.getLogger(__name__)

# Initialize FACEIT API instances
faceit_api = FaceitAPI()
cached_api = CachedFaceitAPI(faceit_api)


def _run_async(coro):
    """Helper to run async code in sync job context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)


def _log_job_start(job_name: str, **kwargs) -> None:
    """Log job start with parameters."""
    job = get_current_job()
    job_id = job.id if job else "unknown"
    logger.info(f"Starting job {job_name} (ID: {job_id}) with params: {kwargs}")


def _log_job_complete(job_name: str, result: Any = None) -> None:
    """Log job completion."""
    job = get_current_job()
    job_id = job.id if job else "unknown"
    logger.info(f"Completed job {job_name} (ID: {job_id})")


def _log_job_error(job_name: str, error: Exception) -> None:
    """Log job error."""
    job = get_current_job()
    job_id = job.id if job else "unknown"
    logger.error(f"Job {job_name} (ID: {job_id}) failed: {error}")


@job('faceit_bot_high', timeout=300)
def analyze_match_job(match_url_or_id: str, user_id: int) -> Dict[str, Any]:
    """Background job for match analysis."""
    _log_job_start("analyze_match", match_url_or_id=match_url_or_id, user_id=user_id)
    
    try:
        # Create analyzer
        analyzer = MatchAnalyzer(faceit_api)
        
        # Run analysis
        result = _run_async(analyzer.analyze_match(match_url_or_id))
        
        if result.get("success"):
            # Format the result for Telegram
            formatted_message = format_match_analysis(result)
            result["formatted_message"] = formatted_message
            result["user_id"] = user_id
            result["timestamp"] = datetime.now().isoformat()
            
            # Store analysis result (optional, for caching)
            analysis_cache_key = f"analysis:{match_url_or_id}:{user_id}"
            _run_async(_store_analysis_result(analysis_cache_key, result))
        
        _log_job_complete("analyze_match", result.get("success"))
        return result
        
    except Exception as e:
        _log_job_error("analyze_match", e)
        return {
            "success": False,
            "error": f"Ошибка анализа: {str(e)}",
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_bot_default', timeout=300)
def generate_player_report_job(player_id: str, user_id: int) -> Dict[str, Any]:
    """Background job for generating detailed player reports."""
    _log_job_start("generate_player_report", player_id=player_id, user_id=user_id)
    
    try:
        # Get player data
        player = _run_async(cached_api.get_player_by_id(player_id))
        if not player:
            return {
                "success": False,
                "error": "Игрок не найден",
                "user_id": user_id
            }
        
        # Get detailed player stats
        matches_with_stats = _run_async(cached_api.get_matches_with_stats(player_id, limit=50))
        
        # Generate comprehensive report
        report = MessageFormatter.format_detailed_player_report(
            player, matches_with_stats[:30]
        )
        
        result = {
            "success": True,
            "player_id": player_id,
            "player_nickname": player.nickname,
            "report": report,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
        
        _log_job_complete("generate_player_report")
        return result
        
    except Exception as e:
        _log_job_error("generate_player_report", e)
        return {
            "success": False,
            "error": f"Ошибка генерации отчёта: {str(e)}",
            "user_id": user_id
        }


@job('faceit_bot_low', timeout=1800)  # 30 minutes for bulk operations
def process_bulk_analysis_job(match_ids: List[str], user_id: int) -> Dict[str, Any]:
    """Background job for bulk match analysis."""
    _log_job_start("process_bulk_analysis", match_count=len(match_ids), user_id=user_id)
    
    try:
        analyzer = MatchAnalyzer(faceit_api)
        results = []
        successful_analyses = 0
        
        for i, match_id in enumerate(match_ids):
            try:
                # Update job progress
                job = get_current_job()
                if job:
                    job.meta['progress'] = f"{i+1}/{len(match_ids)}"
                    job.save_meta()
                
                # Analyze match
                analysis_result = _run_async(analyzer.analyze_match(match_id))
                
                if analysis_result.get("success"):
                    successful_analyses += 1
                    # Format for storage
                    formatted_message = format_match_analysis(analysis_result)
                    analysis_result["formatted_message"] = formatted_message
                
                results.append({
                    "match_id": match_id,
                    "result": analysis_result,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Small delay between analyses to avoid rate limiting
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error analyzing match {match_id}: {e}")
                results.append({
                    "match_id": match_id,
                    "result": {"success": False, "error": str(e)},
                    "timestamp": datetime.now().isoformat()
                })
        
        result = {
            "success": True,
            "total_matches": len(match_ids),
            "successful_analyses": successful_analyses,
            "failed_analyses": len(match_ids) - successful_analyses,
            "results": results,
            "user_id": user_id,
            "completed_at": datetime.now().isoformat()
        }
        
        _log_job_complete("process_bulk_analysis", f"{successful_analyses}/{len(match_ids)} successful")
        return result
        
    except Exception as e:
        _log_job_error("process_bulk_analysis", e)
        return {
            "success": False,
            "error": f"Ошибка массового анализа: {str(e)}",
            "user_id": user_id
        }


@job('faceit_bot_default', timeout=600)
def monitor_matches_job(user_ids: Optional[List[int]] = None) -> Dict[str, Any]:
    """Background job for monitoring new matches."""
    _log_job_start("monitor_matches", user_ids=user_ids)
    
    try:
        from utils.monitor import MatchMonitor
        from bot.bot import bot  # Import bot instance
        
        # Create monitor instance
        monitor = MatchMonitor(bot)
        
        # Get users to monitor
        if user_ids:
            users = []
            for user_id in user_ids:
                user = _run_async(storage.get_user_data(user_id))
                if user and user.faceit_player_id:
                    users.append(user)
        else:
            users = _run_async(storage.get_all_users())
            users = [u for u in users if u.faceit_player_id]
        
        notifications_sent = 0
        errors = 0
        
        for user in users:
            try:
                # Check for new matches
                new_matches = _run_async(faceit_api.check_player_new_matches(
                    user.faceit_player_id,
                    user.last_checked_match_id
                ))
                
                # Send notifications for finished matches
                for match in new_matches:
                    if match.status.upper() == "FINISHED":
                        _run_async(bot.send_match_notification(user.user_id, match.match_id))
                        notifications_sent += 1
                        time.sleep(1)  # Rate limiting
                
                # Update last checked match
                if new_matches:
                    _run_async(storage.update_last_checked_match(
                        user.user_id, new_matches[0].match_id
                    ))
                    
            except Exception as e:
                logger.error(f"Error monitoring user {user.user_id}: {e}")
                errors += 1
        
        result = {
            "success": True,
            "users_monitored": len(users),
            "notifications_sent": notifications_sent,
            "errors": errors,
            "timestamp": datetime.now().isoformat()
        }
        
        _log_job_complete("monitor_matches", f"{notifications_sent} notifications sent")
        return result
        
    except Exception as e:
        _log_job_error("monitor_matches", e)
        return {
            "success": False,
            "error": f"Ошибка мониторинга: {str(e)}"
        }


@job('faceit_bot_low', timeout=600)
def update_player_cache_job(cache_type: str, identifiers: List[str]) -> Dict[str, Any]:
    """Background job for updating player cache."""
    _log_job_start("update_player_cache", cache_type=cache_type, count=len(identifiers))
    
    try:
        updated_count = 0
        errors = 0
        
        for identifier in identifiers:
            try:
                if cache_type == "player":
                    _run_async(cached_api.get_player_by_id(identifier))
                elif cache_type == "player_stats":
                    _run_async(cached_api.get_matches_with_stats(identifier, limit=20))
                elif cache_type == "match":
                    _run_async(cached_api.get_match_details(identifier))
                
                updated_count += 1
                
            except Exception as e:
                logger.error(f"Error updating cache for {identifier}: {e}")
                errors += 1
        
        result = {
            "success": True,
            "cache_type": cache_type,
            "total_items": len(identifiers),
            "updated_count": updated_count,
            "errors": errors,
            "timestamp": datetime.now().isoformat()
        }
        
        _log_job_complete("update_player_cache", f"{updated_count}/{len(identifiers)} updated")
        return result
        
    except Exception as e:
        _log_job_error("update_player_cache", e)
        return {
            "success": False,
            "error": f"Ошибка обновления кэша: {str(e)}"
        }


@job('faceit_bot_low', timeout=300)
def calculate_team_stats_job(team_players: List[str], match_map: Optional[str] = None) -> Dict[str, Any]:
    """Background job for calculating team statistics."""
    _log_job_start("calculate_team_stats", players=len(team_players), match_map=match_map)
    
    try:
        from utils.match_analyzer import MatchAnalyzer
        
        analyzer = MatchAnalyzer(faceit_api)
        team_analysis = _run_async(analyzer._analyze_team(team_players, "Team"))
        
        # Calculate additional team metrics
        team_stats = {
            "average_elo": team_analysis.avg_elo,
            "average_level": team_analysis.avg_level,
            "player_count": len(team_analysis.players),
            "danger_levels": [p.danger_level for p in team_analysis.players],
            "average_danger": sum(p.danger_level for p in team_analysis.players) / len(team_analysis.players),
            "roles": [p.role for p in team_analysis.players],
            "strong_maps": team_analysis.strong_maps,
            "weak_maps": team_analysis.weak_maps
        }
        
        # Map-specific analysis
        if match_map and match_map in team_analysis.team_map_stats:
            map_stats = team_analysis.team_map_stats[match_map]
            team_stats["map_performance"] = {
                "map_name": match_map,
                "winrate": map_stats.get("avg_winrate", 0),
                "avg_kd": map_stats.get("avg_kd", 0),
                "matches_played": map_stats.get("total_matches", 0)
            }
        
        result = {
            "success": True,
            "team_stats": team_stats,
            "timestamp": datetime.now().isoformat()
        }
        
        _log_job_complete("calculate_team_stats")
        return result
        
    except Exception as e:
        _log_job_error("calculate_team_stats", e)
        return {
            "success": False,
            "error": f"Ошибка расчёта статистики команды: {str(e)}"
        }


@job('faceit_bot_low', timeout=900)  # 15 minutes
def generate_analytics_report_job(
    user_id: int, 
    report_type: str = "weekly",
    include_comparisons: bool = True
) -> Dict[str, Any]:
    """Background job for generating analytics reports."""
    _log_job_start("generate_analytics_report", user_id=user_id, report_type=report_type)
    
    try:
        user = _run_async(storage.get_user_data(user_id))
        if not user or not user.faceit_player_id:
            return {
                "success": False,
                "error": "Пользователь не найден или не привязан к FACEIT"
            }
        
        # Get player data
        player = _run_async(cached_api.get_player_by_id(user.faceit_player_id))
        if not player:
            return {
                "success": False,
                "error": "Данные игрока не найдены"
            }
        
        # Determine time period
        if report_type == "weekly":
            limit = 50
            days_back = 7
        elif report_type == "monthly":
            limit = 150
            days_back = 30
        else:  # daily
            limit = 20
            days_back = 1
        
        # Get match data
        matches_with_stats = _run_async(cached_api.get_matches_with_stats(
            user.faceit_player_id, limit=limit
        ))
        
        # Filter by time period
        cutoff_date = datetime.now() - timedelta(days=days_back)
        recent_matches = []
        
        for match, stats in matches_with_stats:
            try:
                match_date = datetime.fromisoformat(match.finished_at.replace('Z', '+00:00'))
                if match_date >= cutoff_date:
                    recent_matches.append((match, stats))
            except (ValueError, AttributeError):
                continue
        
        # Generate analytics
        analytics = MessageFormatter.generate_analytics_report(
            player, recent_matches, report_type
        )
        
        # Add comparison data if requested
        if include_comparisons and len(recent_matches) >= 10:
            comparison_data = _generate_performance_comparison(recent_matches)
            analytics["comparison"] = comparison_data
        
        result = {
            "success": True,
            "user_id": user_id,
            "player_nickname": player.nickname,
            "report_type": report_type,
            "matches_analyzed": len(recent_matches),
            "analytics": analytics,
            "generated_at": datetime.now().isoformat()
        }
        
        _log_job_complete("generate_analytics_report")
        return result
        
    except Exception as e:
        _log_job_error("generate_analytics_report", e)
        return {
            "success": False,
            "error": f"Ошибка генерации аналитики: {str(e)}"
        }


async def _store_analysis_result(cache_key: str, result: Dict[str, Any]) -> None:
    """Store analysis result in cache."""
    try:
        from utils.cache import get_redis_client
        redis_client = await get_redis_client()
        
        # Store for 1 hour
        await redis_client.setex(
            cache_key, 
            3600, 
            json.dumps(result, default=str)
        )
    except Exception as e:
        logger.error(f"Failed to store analysis result: {e}")


def _generate_performance_comparison(matches_with_stats: List[Tuple]) -> Dict[str, Any]:
    """Generate performance comparison data."""
    if len(matches_with_stats) < 10:
        return {}
    
    # Split into recent vs older matches
    mid_point = len(matches_with_stats) // 2
    recent_matches = matches_with_stats[:mid_point]
    older_matches = matches_with_stats[mid_point:]
    
    def calculate_avg_stats(matches):
        total_kills = total_deaths = total_adr = wins = 0
        match_count = len(matches)
        
        for match, stats in matches:
            if not stats:
                continue
            
            # Implementation would depend on MessageFormatter methods
            # This is a simplified version
            total_kills += 1  # Placeholder
            total_deaths += 1  # Placeholder
            total_adr += 50   # Placeholder
        
        return {
            "avg_kd": total_kills / max(total_deaths, 1),
            "avg_adr": total_adr / match_count,
            "winrate": (wins / match_count) * 100
        }
    
    recent_stats = calculate_avg_stats(recent_matches)
    older_stats = calculate_avg_stats(older_matches)
    
    return {
        "recent_period": recent_stats,
        "previous_period": older_stats,
        "improvements": {
            "kd_change": recent_stats["avg_kd"] - older_stats["avg_kd"],
            "adr_change": recent_stats["avg_adr"] - older_stats["avg_adr"],
            "winrate_change": recent_stats["winrate"] - older_stats["winrate"]
        }
    }