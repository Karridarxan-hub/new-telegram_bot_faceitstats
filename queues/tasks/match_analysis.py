"""Background tasks for match analysis operations.

Handles CPU-intensive match analysis work by moving it from the main bot thread
to Redis queues with proper error handling, retry logic, and progress tracking.
"""

import logging
import asyncio
import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

from rq import get_current_job
from rq.decorators import job

from faceit.api import FaceitAPI, FaceitAPIError
from faceit.models import FaceitMatch, FaceitPlayer
from utils.match_analyzer import MatchAnalyzer, format_match_analysis
from utils.formatter import MessageFormatter
from utils.cache import CachedFaceitAPI
from utils.storage import storage
from config.settings import settings

logger = logging.getLogger(__name__)

# Initialize API instances
faceit_api = FaceitAPI()
cached_api = CachedFaceitAPI(faceit_api)


@dataclass
class TaskProgress:
    """Progress tracking for long-running tasks."""
    current_step: int
    total_steps: int
    current_operation: str
    status: str = "running"
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    @property
    def progress_percentage(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return round((self.current_step / self.total_steps) * 100, 1)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _run_async(coro):
    """Helper to run async code in sync job context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(coro)


def _update_job_progress(progress: TaskProgress):
    """Update job progress metadata."""
    job = get_current_job()
    if job:
        job.meta.update({
            'progress': progress.to_dict(),
            'updated_at': datetime.now().isoformat()
        })
        job.save_meta()


def _log_task_start(task_name: str, **kwargs):
    """Log task start with parameters."""
    job = get_current_job()
    job_id = job.id if job else "unknown"
    logger.info(f"Starting {task_name} task (ID: {job_id}) with params: {kwargs}")


def _log_task_complete(task_name: str, result: Any = None):
    """Log task completion."""
    job = get_current_job()
    job_id = job.id if job else "unknown"
    logger.info(f"Completed {task_name} task (ID: {job_id})")


def _log_task_error(task_name: str, error: Exception):
    """Log task error."""
    job = get_current_job()
    job_id = job.id if job else "unknown"
    logger.error(f"Task {task_name} (ID: {job_id}) failed: {error}")


@job('faceit_match_analysis', timeout=600, result_ttl=3600)
def analyze_match_task(
    match_url_or_id: str, 
    user_id: int, 
    force_refresh: bool = False
) -> Dict[str, Any]:
    """
    Background task for comprehensive match analysis.
    
    This task moves the CPU-intensive match analysis work from the main bot thread
    to a background queue, allowing the bot to remain responsive while processing.
    
    Args:
        match_url_or_id: FACEIT match URL or ID
        user_id: Telegram user ID requesting analysis
        force_refresh: Whether to bypass cache
        
    Returns:
        Dict with analysis results and formatted message
    """
    _log_task_start("analyze_match", match_url_or_id=match_url_or_id, user_id=user_id)
    
    progress = TaskProgress(
        current_step=0,
        total_steps=6,
        current_operation="Initializing analysis..."
    )
    _update_job_progress(progress)
    
    try:
        # Step 1: Initialize analyzer
        progress.current_step = 1
        progress.current_operation = "Setting up match analyzer..."
        _update_job_progress(progress)
        
        analyzer = MatchAnalyzer(faceit_api)
        
        # Step 2: Parse and validate match URL
        progress.current_step = 2
        progress.current_operation = "Parsing match URL..."
        _update_job_progress(progress)
        
        if 'faceit.com' in match_url_or_id:
            match_id = analyzer.parse_faceit_url(match_url_or_id)
            if not match_id:
                return {
                    "success": False,
                    "error": "Invalid FACEIT match URL format",
                    "user_id": user_id,
                    "timestamp": datetime.now().isoformat()
                }
        else:
            match_id = match_url_or_id
        
        # Step 3: Perform match analysis
        progress.current_step = 3
        progress.current_operation = "Analyzing match teams and players..."
        _update_job_progress(progress)
        
        analysis_result = _run_async(analyzer.analyze_match(match_id))
        
        if not analysis_result.get("success"):
            return {
                "success": False,
                "error": analysis_result.get("error", "Analysis failed"),
                "user_id": user_id,
                "timestamp": datetime.now().isoformat()
            }
        
        # Step 4: Format results
        progress.current_step = 4
        progress.current_operation = "Formatting analysis results..."
        _update_job_progress(progress)
        
        formatted_message = format_match_analysis(analysis_result)
        
        # Step 5: Store results
        progress.current_step = 5
        progress.current_operation = "Caching analysis results..."
        _update_job_progress(progress)
        
        # Cache the analysis for quick retrieval
        cache_key = f"analysis:{match_id}:{user_id}"
        cached_result = {
            "analysis_result": analysis_result,
            "formatted_message": formatted_message,
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id
        }
        
        _run_async(_cache_analysis_result(cache_key, cached_result))
        
        # Step 6: Finalize
        progress.current_step = 6
        progress.current_operation = "Analysis complete!"
        progress.status = "completed"
        _update_job_progress(progress)
        
        result = {
            "success": True,
            "match_id": match_id,
            "analysis_result": analysis_result,
            "formatted_message": formatted_message,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "processing_steps": progress.current_step
        }
        
        _log_task_complete("analyze_match")
        return result
        
    except FaceitAPIError as e:
        _log_task_error("analyze_match", e)
        progress.status = "failed"
        progress.errors.append(f"FACEIT API error: {str(e)}")
        _update_job_progress(progress)
        
        return {
            "success": False,
            "error": f"FACEIT API error: {str(e)}",
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        _log_task_error("analyze_match", e)
        progress.status = "failed"
        progress.errors.append(f"Unexpected error: {str(e)}")
        _update_job_progress(progress)
        
        return {
            "success": False,
            "error": f"Analysis failed: {str(e)}",
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_bulk_analysis', timeout=3600, result_ttl=7200)
def bulk_analyze_matches_task(
    match_urls: List[str], 
    user_id: int,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Background task for bulk match analysis.
    
    Processes multiple matches in parallel with rate limiting to avoid API limits.
    Provides detailed progress tracking for long-running operations.
    
    Args:
        match_urls: List of FACEIT match URLs or IDs
        user_id: Telegram user ID
        options: Optional processing options
        
    Returns:
        Dict with bulk analysis results
    """
    _log_task_start("bulk_analyze_matches", match_count=len(match_urls), user_id=user_id)
    
    options = options or {}
    max_concurrent = options.get('max_concurrent', 3)
    delay_between_batches = options.get('delay_seconds', 2)
    
    progress = TaskProgress(
        current_step=0,
        total_steps=len(match_urls),
        current_operation="Starting bulk analysis..."
    )
    _update_job_progress(progress)
    
    try:
        analyzer = MatchAnalyzer(faceit_api)
        results = []
        successful_analyses = 0
        failed_analyses = 0
        
        # Process matches in batches to avoid overwhelming the API
        for i in range(0, len(match_urls), max_concurrent):
            batch = match_urls[i:i + max_concurrent]
            batch_results = []
            
            progress.current_operation = f"Processing batch {i//max_concurrent + 1}..."
            _update_job_progress(progress)
            
            # Process batch
            for j, match_url in enumerate(batch):
                progress.current_step = i + j + 1
                progress.current_operation = f"Analyzing match {progress.current_step}/{len(match_urls)}"
                _update_job_progress(progress)
                
                try:
                    # Parse match ID
                    if 'faceit.com' in match_url:
                        match_id = analyzer.parse_faceit_url(match_url)
                    else:
                        match_id = match_url
                    
                    if not match_id:
                        batch_results.append({
                            "match_url": match_url,
                            "success": False,
                            "error": "Invalid URL format",
                            "timestamp": datetime.now().isoformat()
                        })
                        failed_analyses += 1
                        continue
                    
                    # Perform analysis
                    analysis_result = _run_async(analyzer.analyze_match(match_id))
                    
                    if analysis_result.get("success"):
                        # Format message
                        formatted_message = format_match_analysis(analysis_result)
                        
                        batch_results.append({
                            "match_url": match_url,
                            "match_id": match_id,
                            "success": True,
                            "analysis_result": analysis_result,
                            "formatted_message": formatted_message,
                            "timestamp": datetime.now().isoformat()
                        })
                        successful_analyses += 1
                    else:
                        batch_results.append({
                            "match_url": match_url,
                            "match_id": match_id,
                            "success": False,
                            "error": analysis_result.get("error", "Analysis failed"),
                            "timestamp": datetime.now().isoformat()
                        })
                        failed_analyses += 1
                    
                    # Small delay to avoid hitting rate limits
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error analyzing match {match_url}: {e}")
                    batch_results.append({
                        "match_url": match_url,
                        "success": False,
                        "error": f"Processing error: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    })
                    failed_analyses += 1
            
            results.extend(batch_results)
            
            # Delay between batches
            if i + max_concurrent < len(match_urls):
                time.sleep(delay_between_batches)
        
        progress.status = "completed"
        progress.current_operation = f"Bulk analysis complete! {successful_analyses} successful, {failed_analyses} failed"
        _update_job_progress(progress)
        
        result = {
            "success": True,
            "total_matches": len(match_urls),
            "successful_analyses": successful_analyses,
            "failed_analyses": failed_analyses,
            "success_rate": round((successful_analyses / len(match_urls)) * 100, 1),
            "results": results,
            "user_id": user_id,
            "completed_at": datetime.now().isoformat(),
            "processing_options": options
        }
        
        # Cache bulk results
        cache_key = f"bulk_analysis:{user_id}:{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        _run_async(_cache_analysis_result(cache_key, result, ttl=7200))
        
        _log_task_complete("bulk_analyze_matches", f"{successful_analyses}/{len(match_urls)} successful")
        return result
        
    except Exception as e:
        _log_task_error("bulk_analyze_matches", e)
        progress.status = "failed"
        progress.errors.append(str(e))
        _update_job_progress(progress)
        
        return {
            "success": False,
            "error": f"Bulk analysis failed: {str(e)}",
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }


@job('faceit_team_stats', timeout=900, result_ttl=1800)
def calculate_team_stats_task(
    team_player_ids: List[str],
    team_name: str,
    match_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Background task for calculating comprehensive team statistics.
    
    Args:
        team_player_ids: List of FACEIT player IDs in the team
        team_name: Name of the team
        match_context: Optional match context (map, competition, etc.)
        
    Returns:
        Dict with comprehensive team statistics
    """
    _log_task_start("calculate_team_stats", team=team_name, players=len(team_player_ids))
    
    progress = TaskProgress(
        current_step=0,
        total_steps=len(team_player_ids) + 3,
        current_operation="Starting team analysis..."
    )
    _update_job_progress(progress)
    
    try:
        analyzer = MatchAnalyzer(faceit_api)
        
        # Step 1: Gather player data in parallel
        progress.current_step = 1
        progress.current_operation = "Gathering player data..."
        _update_job_progress(progress)
        
        player_data = []
        for i, player_id in enumerate(team_player_ids):
            progress.current_step = i + 2
            progress.current_operation = f"Analyzing player {i+1}/{len(team_player_ids)}"
            _update_job_progress(progress)
            
            try:
                player_analysis = _run_async(analyzer._analyze_single_player(player_id))
                if player_analysis:
                    player_data.append(player_analysis)
            except Exception as e:
                logger.warning(f"Failed to analyze player {player_id}: {e}")
                progress.errors.append(f"Player {player_id}: {str(e)}")
        
        if not player_data:
            return {
                "success": False,
                "error": "No player data could be retrieved",
                "team_name": team_name
            }
        
        # Step 2: Calculate team metrics
        progress.current_step = len(team_player_ids) + 2
        progress.current_operation = "Calculating team metrics..."
        _update_job_progress(progress)
        
        team_metrics = _calculate_comprehensive_team_stats(player_data, match_context)
        
        # Step 3: Generate insights
        progress.current_step = len(team_player_ids) + 3
        progress.current_operation = "Generating team insights..."
        progress.status = "completed"
        _update_job_progress(progress)
        
        team_insights = _generate_team_insights(player_data, team_metrics)
        
        result = {
            "success": True,
            "team_name": team_name,
            "player_count": len(player_data),
            "metrics": team_metrics,
            "insights": team_insights,
            "players": player_data,
            "match_context": match_context,
            "timestamp": datetime.now().isoformat()
        }
        
        _log_task_complete("calculate_team_stats")
        return result
        
    except Exception as e:
        _log_task_error("calculate_team_stats", e)
        progress.status = "failed"
        progress.errors.append(str(e))
        _update_job_progress(progress)
        
        return {
            "success": False,
            "error": f"Team stats calculation failed: {str(e)}",
            "team_name": team_name
        }


@job('faceit_player_performance', timeout=600, result_ttl=1800)
def analyze_player_performance_task(
    player_id: str,
    analysis_period_days: int = 30,
    include_detailed_stats: bool = True
) -> Dict[str, Any]:
    """
    Background task for comprehensive player performance analysis.
    
    Args:
        player_id: FACEIT player ID
        analysis_period_days: Number of days to analyze
        include_detailed_stats: Whether to include detailed statistics
        
    Returns:
        Dict with player performance analysis
    """
    _log_task_start("analyze_player_performance", player_id=player_id, period=analysis_period_days)
    
    progress = TaskProgress(
        current_step=0,
        total_steps=8,
        current_operation="Starting player analysis..."
    )
    _update_job_progress(progress)
    
    try:
        # Step 1: Get player info
        progress.current_step = 1
        progress.current_operation = "Fetching player information..."
        _update_job_progress(progress)
        
        player = _run_async(cached_api.get_player_by_id(player_id))
        if not player:
            return {
                "success": False,
                "error": "Player not found",
                "player_id": player_id
            }
        
        # Step 2: Get match history
        progress.current_step = 2
        progress.current_operation = "Fetching match history..."
        _update_job_progress(progress)
        
        match_limit = min(200, analysis_period_days * 5)  # Estimate 5 matches per day max
        matches_with_stats = _run_async(cached_api.get_matches_with_stats(player_id, limit=match_limit))
        
        # Step 3: Filter by time period
        progress.current_step = 3
        progress.current_operation = "Filtering matches by time period..."
        _update_job_progress(progress)
        
        cutoff_date = datetime.now() - timedelta(days=analysis_period_days)
        recent_matches = []
        
        for match, stats in matches_with_stats:
            try:
                if hasattr(match, 'finished_at') and match.finished_at:
                    match_date = datetime.fromisoformat(match.finished_at.replace('Z', '+00:00'))
                    if match_date >= cutoff_date:
                        recent_matches.append((match, stats))
            except (ValueError, AttributeError):
                continue
        
        # Step 4: Calculate basic performance metrics
        progress.current_step = 4
        progress.current_operation = "Calculating performance metrics..."
        _update_job_progress(progress)
        
        performance_metrics = _calculate_detailed_player_performance(recent_matches, player_id)
        
        # Step 5: Analyze trends
        progress.current_step = 5
        progress.current_operation = "Analyzing performance trends..."
        _update_job_progress(progress)
        
        trend_analysis = _analyze_performance_trends(recent_matches, player_id)
        
        # Step 6: Map performance analysis
        progress.current_step = 6
        progress.current_operation = "Analyzing map performance..."
        _update_job_progress(progress)
        
        from utils.map_analyzer import MapAnalyzer
        map_performance = MapAnalyzer.analyze_player_maps(recent_matches, player_id)
        
        # Step 7: Weapon/playstyle analysis
        progress.current_step = 7
        progress.current_operation = "Analyzing playstyle..."
        _update_job_progress(progress)
        
        from utils.map_analyzer import WeaponAnalyzer
        playstyle_analysis = WeaponAnalyzer.analyze_player_playstyle(recent_matches, player_id)
        
        # Step 8: Generate insights and recommendations
        progress.current_step = 8
        progress.current_operation = "Generating insights..."
        progress.status = "completed"
        _update_job_progress(progress)
        
        insights = _generate_player_insights(performance_metrics, trend_analysis, map_performance, playstyle_analysis)
        
        result = {
            "success": True,
            "player": {
                "player_id": player.player_id,
                "nickname": player.nickname,
                "country": player.country,
                "skill_level": player.games.get('cs2', {}).skill_level if player.games.get('cs2') else 0,
                "faceit_elo": player.games.get('cs2', {}).faceit_elo if player.games.get('cs2') else 0
            },
            "analysis_period": {
                "days": analysis_period_days,
                "matches_analyzed": len(recent_matches),
                "cutoff_date": cutoff_date.isoformat()
            },
            "performance": performance_metrics,
            "trends": trend_analysis,
            "map_performance": map_performance,
            "playstyle": playstyle_analysis,
            "insights": insights,
            "timestamp": datetime.now().isoformat()
        }
        
        _log_task_complete("analyze_player_performance")
        return result
        
    except Exception as e:
        _log_task_error("analyze_player_performance", e)
        progress.status = "failed"
        progress.errors.append(str(e))
        _update_job_progress(progress)
        
        return {
            "success": False,
            "error": f"Player performance analysis failed: {str(e)}",
            "player_id": player_id
        }


@job('faceit_match_report', timeout=300, result_ttl=1800)
def generate_match_report_task(
    match_id: str,
    report_type: str = "standard",
    include_predictions: bool = True
) -> Dict[str, Any]:
    """
    Background task for generating detailed match reports.
    
    Args:
        match_id: FACEIT match ID
        report_type: Type of report (standard, detailed, tactical)
        include_predictions: Whether to include match predictions
        
    Returns:
        Dict with formatted match report
    """
    _log_task_start("generate_match_report", match_id=match_id, report_type=report_type)
    
    try:
        # Get match details
        match = _run_async(faceit_api.get_match_details(match_id))
        if not match:
            return {
                "success": False,
                "error": "Match not found",
                "match_id": match_id
            }
        
        # Perform analysis based on report type
        if report_type == "detailed":
            analyzer = MatchAnalyzer(faceit_api)
            analysis_result = _run_async(analyzer.analyze_match(match_id))
            
            if not analysis_result.get("success"):
                return {
                    "success": False,
                    "error": analysis_result.get("error", "Analysis failed"),
                    "match_id": match_id
                }
            
            # Generate detailed report
            report = _generate_detailed_match_report(match, analysis_result, include_predictions)
        
        elif report_type == "tactical":
            # Focus on tactical insights
            analyzer = MatchAnalyzer(faceit_api)
            analysis_result = _run_async(analyzer.analyze_match(match_id))
            
            if not analysis_result.get("success"):
                return {
                    "success": False,
                    "error": analysis_result.get("error", "Analysis failed"),
                    "match_id": match_id
                }
            
            report = _generate_tactical_match_report(match, analysis_result)
        
        else:  # standard
            # Basic match information report
            report = _generate_standard_match_report(match)
        
        result = {
            "success": True,
            "match_id": match_id,
            "report_type": report_type,
            "report": report,
            "include_predictions": include_predictions,
            "generated_at": datetime.now().isoformat()
        }
        
        _log_task_complete("generate_match_report")
        return result
        
    except Exception as e:
        _log_task_error("generate_match_report", e)
        return {
            "success": False,
            "error": f"Report generation failed: {str(e)}",
            "match_id": match_id
        }


# Helper functions

async def _cache_analysis_result(cache_key: str, result: Dict[str, Any], ttl: int = 3600):
    """Cache analysis result in Redis."""
    try:
        from utils.redis_cache import get_redis_client
        redis_client = await get_redis_client()
        
        await redis_client.setex(
            cache_key,
            ttl,
            json.dumps(result, default=str)
        )
        logger.debug(f"Cached analysis result: {cache_key}")
    except Exception as e:
        logger.error(f"Failed to cache analysis result: {e}")


def _calculate_comprehensive_team_stats(player_data: List[Dict], match_context: Optional[Dict] = None) -> Dict[str, Any]:
    """Calculate comprehensive team statistics."""
    if not player_data:
        return {}
    
    # Extract metrics from player data
    total_elo = sum(p.player.games.get('cs2', {}).faceit_elo for p in player_data if hasattr(p, 'player'))
    total_skill_level = sum(p.player.games.get('cs2', {}).skill_level for p in player_data if hasattr(p, 'player'))
    
    # Calculate averages
    player_count = len(player_data)
    avg_elo = round(total_elo / player_count) if player_count > 0 else 0
    avg_skill_level = round(total_skill_level / player_count, 1) if player_count > 0 else 0
    
    # Performance metrics
    total_winrate = sum(getattr(p, 'winrate', 0) for p in player_data)
    total_kd = sum(getattr(p, 'avg_kd', 0) for p in player_data)
    total_hltv = sum(getattr(p, 'hltv_rating', 0) for p in player_data)
    
    team_winrate = round(total_winrate / player_count, 1) if player_count > 0 else 0
    team_kd = round(total_kd / player_count, 2) if player_count > 0 else 0
    team_hltv = round(total_hltv / player_count, 2) if player_count > 0 else 0
    
    # Danger level analysis
    danger_levels = [getattr(p, 'danger_level', 1) for p in player_data]
    avg_danger = round(sum(danger_levels) / len(danger_levels), 1)
    high_danger_count = len([d for d in danger_levels if d >= 4])
    
    return {
        "player_count": player_count,
        "avg_elo": avg_elo,
        "avg_skill_level": avg_skill_level,
        "team_winrate": team_winrate,
        "team_kd": team_kd,
        "team_hltv_rating": team_hltv,
        "avg_danger_level": avg_danger,
        "high_danger_players": high_danger_count,
        "elo_range": {
            "min": min(p.player.games.get('cs2', {}).faceit_elo for p in player_data if hasattr(p, 'player')),
            "max": max(p.player.games.get('cs2', {}).faceit_elo for p in player_data if hasattr(p, 'player'))
        } if player_data else {"min": 0, "max": 0}
    }


def _generate_team_insights(player_data: List[Dict], team_metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Generate team insights and recommendations."""
    insights = {
        "strengths": [],
        "weaknesses": [],
        "recommendations": [],
        "key_players": []
    }
    
    # Identify strengths
    if team_metrics.get("team_hltv_rating", 0) > 1.1:
        insights["strengths"].append("High individual skill level")
    
    if team_metrics.get("team_winrate", 0) > 60:
        insights["strengths"].append("Strong recent form")
    
    if team_metrics.get("high_danger_players", 0) >= 2:
        insights["strengths"].append("Multiple high-impact players")
    
    # Identify weaknesses
    if team_metrics.get("team_kd", 0) < 1.0:
        insights["weaknesses"].append("Negative K/D ratio")
    
    if team_metrics.get("avg_danger_level", 0) < 2.5:
        insights["weaknesses"].append("Low overall threat level")
    
    # Key players
    sorted_players = sorted(
        player_data,
        key=lambda x: getattr(x, 'danger_level', 1) * getattr(x, 'hltv_rating', 0),
        reverse=True
    )
    
    insights["key_players"] = [
        {
            "nickname": p.player.nickname if hasattr(p, 'player') else "Unknown",
            "role": getattr(p, 'role', 'Unknown'),
            "danger_level": getattr(p, 'danger_level', 1),
            "hltv_rating": getattr(p, 'hltv_rating', 0)
        }
        for p in sorted_players[:3]
    ]
    
    return insights


def _calculate_detailed_player_performance(matches_with_stats: List[Tuple], player_id: str) -> Dict[str, Any]:
    """Calculate detailed player performance metrics."""
    if not matches_with_stats:
        return {}
    
    finished_matches = [
        (match, stats) for match, stats in matches_with_stats
        if match.status.upper() == "FINISHED"
    ]
    
    if not finished_matches:
        return {}
    
    # Basic stats
    total_matches = len(finished_matches)
    wins = 0
    total_kills = total_deaths = total_assists = 0
    total_adr = total_hs = 0.0
    
    # Advanced stats
    mvp_count = 0
    first_kills = 0
    clutch_attempts = 0
    clutch_wins = 0
    
    for match, stats in finished_matches:
        # Win/loss
        player_faction = MessageFormatter._get_player_faction(match, player_id)
        is_win = player_faction == match.results.winner if match.results else False
        wins += 1 if is_win else 0
        
        # Get player stats
        if stats:
            player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
            if player_stats:
                stats_dict = player_stats.player_stats
                total_kills += int(stats_dict.get('Kills', '0'))
                total_deaths += int(stats_dict.get('Deaths', '0'))
                total_assists += int(stats_dict.get('Assists', '0'))
                total_adr += float(stats_dict.get('ADR', '0'))
                total_hs += int(stats_dict.get('Headshots', '0'))
                
                # MVP tracking
                if stats_dict.get('MVP', '0') == '1':
                    mvp_count += 1
    
    # Calculate metrics
    winrate = round((wins / total_matches) * 100, 1) if total_matches > 0 else 0
    avg_kd = round(total_kills / max(total_deaths, 1), 2)
    avg_adr = round(total_adr / total_matches, 1) if total_matches > 0 else 0
    hs_percentage = round((total_hs / max(total_kills, 1)) * 100, 1)
    mvp_rate = round((mvp_count / total_matches) * 100, 1) if total_matches > 0 else 0
    
    # HLTV rating
    hltv_rating = MessageFormatter._calculate_hltv_rating_from_stats(finished_matches, player_id)
    
    return {
        "total_matches": total_matches,
        "winrate": winrate,
        "avg_kd": avg_kd,
        "avg_adr": avg_adr,
        "headshot_percentage": hs_percentage,
        "mvp_rate": mvp_rate,
        "hltv_rating": hltv_rating,
        "total_kills": total_kills,
        "total_deaths": total_deaths,
        "total_assists": total_assists,
        "kda_ratio": round((total_kills + total_assists) / max(total_deaths, 1), 2)
    }


def _analyze_performance_trends(matches_with_stats: List[Tuple], player_id: str) -> Dict[str, Any]:
    """Analyze player performance trends over time."""
    if len(matches_with_stats) < 10:
        return {"error": "Insufficient data for trend analysis"}
    
    # Split matches into periods
    recent_period = matches_with_stats[:len(matches_with_stats)//3]
    older_period = matches_with_stats[len(matches_with_stats)//3:]
    
    recent_perf = _calculate_detailed_player_performance(recent_period, player_id)
    older_perf = _calculate_detailed_player_performance(older_period, player_id)
    
    # Calculate changes
    trends = {
        "period_comparison": {
            "recent_matches": len(recent_period),
            "older_matches": len(older_period)
        },
        "performance_changes": {}
    }
    
    metrics_to_compare = ['winrate', 'avg_kd', 'avg_adr', 'hltv_rating']
    
    for metric in metrics_to_compare:
        recent_val = recent_perf.get(metric, 0)
        older_val = older_perf.get(metric, 0)
        
        if older_val > 0:
            change = recent_val - older_val
            change_percentage = round((change / older_val) * 100, 1)
            
            trends["performance_changes"][metric] = {
                "recent": recent_val,
                "previous": older_val,
                "change": round(change, 2),
                "change_percentage": change_percentage,
                "trend": "improving" if change > 0 else "declining" if change < 0 else "stable"
            }
    
    return trends


def _generate_player_insights(performance: Dict, trends: Dict, map_perf: Dict, playstyle: Dict) -> Dict[str, Any]:
    """Generate comprehensive player insights."""
    insights = {
        "overall_assessment": "",
        "strengths": [],
        "areas_for_improvement": [],
        "recommendations": [],
        "form_analysis": ""
    }
    
    # Overall assessment
    hltv_rating = performance.get("hltv_rating", 0)
    if hltv_rating >= 1.2:
        insights["overall_assessment"] = "Excellent player with consistent high performance"
    elif hltv_rating >= 1.0:
        insights["overall_assessment"] = "Solid player with good fundamentals"
    elif hltv_rating >= 0.9:
        insights["overall_assessment"] = "Average player with potential for improvement"
    else:
        insights["overall_assessment"] = "Struggling player who needs significant improvement"
    
    # Strengths
    if performance.get("headshot_percentage", 0) > 50:
        insights["strengths"].append("Excellent aim and precision")
    
    if performance.get("avg_adr", 0) > 80:
        insights["strengths"].append("Consistent damage output")
    
    if performance.get("mvp_rate", 0) > 15:
        insights["strengths"].append("Clutch player with high impact")
    
    # Areas for improvement
    if performance.get("avg_kd", 0) < 1.0:
        insights["areas_for_improvement"].append("Needs to improve survival and trade efficiency")
    
    if performance.get("winrate", 0) < 50:
        insights["areas_for_improvement"].append("Needs to work on team coordination and game sense")
    
    # Form analysis
    if trends and "performance_changes" in trends:
        improving_metrics = [
            metric for metric, data in trends["performance_changes"].items()
            if data.get("trend") == "improving"
        ]
        
        if len(improving_metrics) >= 2:
            insights["form_analysis"] = "Player is in good form with improving performance"
        elif len(improving_metrics) == 1:
            insights["form_analysis"] = "Player shows mixed form with some improvement"
        else:
            insights["form_analysis"] = "Player may be in a slump, needs focus on fundamentals"
    
    return insights


def _generate_detailed_match_report(match: FaceitMatch, analysis_result: Dict, include_predictions: bool) -> str:
    """Generate detailed match report."""
    # This would use the existing format_match_analysis function
    # but with additional details
    base_report = format_match_analysis(analysis_result)
    
    # Add additional sections for detailed report
    additional_info = []
    
    if include_predictions:
        additional_info.append("\n🔮 <b>MATCH PREDICTIONS:</b>")
        # Add prediction logic here
    
    additional_info.append(f"\n📊 <b>MATCH DETAILS:</b>")
    additional_info.append(f"• Competition: {match.competition_name}")
    additional_info.append(f"• Region: {match.region}")
    additional_info.append(f"• Status: {match.status}")
    
    return base_report + "\n".join(additional_info)


def _generate_tactical_match_report(match: FaceitMatch, analysis_result: Dict) -> str:
    """Generate tactical-focused match report."""
    # Focus on tactical insights, map analysis, and strategic recommendations
    report_parts = []
    
    report_parts.append("⚔️ <b>TACTICAL ANALYSIS</b>\n")
    
    # Add team tactical analysis
    if "team_analyses" in analysis_result:
        for team_name, team_data in analysis_result["team_analyses"].items():
            report_parts.append(f"🎯 <b>{team_name} Tactical Profile:</b>")
            # Add tactical insights
    
    return "\n".join(report_parts)


def _generate_standard_match_report(match: FaceitMatch) -> str:
    """Generate standard match report."""
    report = f"📋 <b>MATCH REPORT</b>\n\n"
    report += f"🏆 <b>{match.competition_name}</b>\n"
    report += f"🌍 Region: {match.region}\n"
    report += f"⚡ Status: {match.status}\n\n"
    
    # Add team information
    for team_name, team_data in match.teams.items():
        report += f"👥 <b>{team_name}:</b>\n"
        for player in team_data.players:
            report += f"• {player.nickname}\n"
        report += "\n"
    
    return report