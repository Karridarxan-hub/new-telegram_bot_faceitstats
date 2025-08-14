"""
Match Service implementation with analysis and processing.

Provides comprehensive match analysis functionality:
- Match analysis orchestration and coordination
- FACEIT API integration with caching
- Team and player analysis processing
- Match prediction and insights generation
- Performance optimization with parallel processing
- Analysis history tracking and management
- Cache management and invalidation
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import uuid
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor

from database.repositories.match import MatchRepository, MatchCacheRepository
from database.repositories.user import UserRepository
from database.models import MatchAnalysis, MatchStatus
from faceit.api import FaceitAPI, FaceitAPIError
from faceit.models import FaceitMatch, FaceitPlayer
from utils.match_analyzer import MatchAnalyzer, PlayerAnalysis, TeamAnalysis
from utils.formatter import MessageFormatter
from utils.map_analyzer import MapAnalyzer, WeaponAnalyzer
from utils.cache import CachedFaceitAPI
from utils.redis_cache import match_cache, stats_cache
from .base import (
    BaseService, ServiceResult, ServiceError, ValidationError,
    BusinessRuleError, EventType
)

logger = logging.getLogger(__name__)


class MatchService(BaseService):
    """
    Service for match analysis and processing.
    
    Handles:
    - Match URL parsing and validation
    - Comprehensive team and player analysis
    - Match predictions and insights
    - Performance optimization with caching
    - Analysis history management
    - Background match monitoring
    - Integration with FACEIT API
    """
    
    def __init__(
        self,
        match_repository: MatchRepository,
        match_cache_repository: MatchCacheRepository,
        user_repository: UserRepository,
        faceit_api: FaceitAPI,
        cache=None
    ):
        super().__init__(cache or match_cache)
        self.match_repo = match_repository
        self.match_cache_repo = match_cache_repository
        self.user_repo = user_repository
        self.faceit_api = faceit_api
        self.cached_api = CachedFaceitAPI(faceit_api)
        self.match_analyzer = MatchAnalyzer(faceit_api)
        
        # Register repositories
        self.register_repository("match", match_repository)
        self.register_repository("match_cache", match_cache_repository)
        self.register_repository("user", user_repository)
        
        # Thread pool for CPU-intensive analysis tasks
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
    
    # Core match analysis
    async def analyze_match(
        self,
        telegram_user_id: int,
        match_url_or_id: str,
        force_refresh: bool = False
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Perform comprehensive match analysis.
        
        Args:
            telegram_user_id: User requesting the analysis
            match_url_or_id: FACEIT match URL or ID
            force_refresh: Force refresh of cached data
            
        Returns:
            ServiceResult with analysis data and formatted message
        """
        try:
            # Get user
            user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Parse match ID from URL
            match_id = self._parse_match_id(match_url_or_id)
            if not match_id:
                return ServiceResult.validation_error(
                    "Invalid FACEIT match URL or ID format",
                    "match_url_or_id"
                )
            
            # Check if analysis already exists (unless force refresh)
            if not force_refresh:
                existing_analysis = await self.match_repo.get_by_match_id(match_id, user.id)
                if existing_analysis and existing_analysis.created_at > datetime.now() - timedelta(hours=1):
                    # Return cached analysis if less than 1 hour old
                    formatted_message = await self._format_existing_analysis(existing_analysis)
                    return ServiceResult.success_result({
                        "analysis": existing_analysis,
                        "formatted_message": formatted_message,
                        "cached": True
                    })
            
            # Perform analysis
            result, processing_time = await self.measure_performance(
                "analyze_match",
                self._perform_match_analysis,
                user.id,
                match_id,
                match_url_or_id,
                force_refresh
            )
            
            # Publish event
            await self.publish_event(
                EventType.MATCH_ANALYZED,
                user.id,
                {
                    "match_id": match_id,
                    "processing_time_ms": processing_time,
                    "cached_data_used": result.get("cached_data_used", False)
                }
            )
            
            return ServiceResult.success_result(
                result,
                metadata={"match_id": match_id},
                processing_time_ms=processing_time
            )
            
        except ValidationError as e:
            return ServiceResult.error_result(e)
        except Exception as e:
            logger.error(f"Error in match analysis: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Match analysis failed: {e}", "MATCH_ANALYSIS_ERROR")
            )
    
    async def _perform_match_analysis(
        self,
        user_id: uuid.UUID,
        match_id: str,
        match_url: str,
        force_refresh: bool
    ) -> Dict[str, Any]:
        """Perform the actual match analysis."""
        start_time = datetime.now()
        cached_data_used = False
        
        try:
            # Get match data (with caching)
            match_data = None
            if not force_refresh:
                cached_match = await self.match_cache_repo.get_cached_match(match_id)
                if cached_match:
                    match_data = cached_match.match_data
                    cached_data_used = True
            
            # Fetch fresh data if needed
            if not match_data:
                match = await self.faceit_api.get_match_details(match_id)
                if not match:
                    raise ValueError(f"Match {match_id} not found")
                
                match_data = match.dict()
                
                # Cache the match data
                await self.match_cache_repo.cache_match_data(
                    match_id, match_data, ttl_minutes=30
                )
            else:
                # Convert cached data back to match object
                match = FaceitMatch(**match_data)
            
            # Validate match status
            if match.status and match.status.upper() == "FINISHED":
                raise BusinessRuleError("Match has already finished", "MATCH_FINISHED")
            
            # Perform team analysis in parallel
            analysis_result = await self._analyze_teams_parallel(match)
            
            # Generate insights and predictions
            insights = self._generate_match_insights(
                analysis_result["team_analyses"], 
                match
            )
            
            # Create comprehensive analysis data
            analysis_data = {
                "match_info": {
                    "match_id": match_id,
                    "status": match.status,
                    "game": "cs2",
                    "region": match.region,
                    "competition_name": match.competition_name,
                    "competition_type": getattr(match, 'competition_type', None),
                    "configured_at": match.configured_at,
                    "started_at": getattr(match, 'started_at', None),
                    "finished_at": getattr(match, 'finished_at', None)
                },
                "team1_analysis": analysis_result["team_analyses"]["team1"],
                "team2_analysis": analysis_result["team_analyses"]["team2"],
                "prediction": insights,
                "cached_data_used": cached_data_used,
                "match_url": match_url
            }
            
            # Store analysis in database
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            match_analysis = await self.match_repo.create_analysis(
                user_id=user_id,
                match_id=match_id,
                analysis_data=analysis_data,
                processing_time_ms=processing_time
            )
            
            # Format message for response
            formatted_message = self._format_analysis_message(analysis_data)
            
            return {
                "analysis": match_analysis,
                "analysis_data": analysis_data,
                "formatted_message": formatted_message,
                "processing_time_ms": processing_time,
                "cached_data_used": cached_data_used
            }
            
        except Exception as e:
            logger.error(f"Match analysis failed for {match_id}: {e}")
            raise
    
    async def _analyze_teams_parallel(self, match: FaceitMatch) -> Dict[str, Any]:
        """Analyze both teams in parallel for better performance."""
        team_names = list(match.teams.keys())
        if len(team_names) != 2:
            raise BusinessRuleError("Match must have exactly 2 teams", "INVALID_TEAM_COUNT")
        
        # Create team analysis tasks
        team1_task = self._analyze_single_team(match.teams[team_names[0]], team_names[0])
        team2_task = self._analyze_single_team(match.teams[team_names[1]], team_names[1])
        
        # Execute in parallel
        try:
            team1_analysis, team2_analysis = await asyncio.gather(
                team1_task, team2_task, return_exceptions=False
            )
            
            return {
                "team_analyses": {
                    "team1": team1_analysis,
                    "team2": team2_analysis
                },
                "team_names": team_names
            }
            
        except Exception as e:
            logger.error(f"Error in parallel team analysis: {e}")
            raise BusinessRuleError(f"Team analysis failed: {e}", "TEAM_ANALYSIS_ERROR")
    
    async def _analyze_single_team(self, team_data: Any, team_name: str) -> Dict[str, Any]:
        """Analyze a single team."""
        try:
            # Extract player data
            players = team_data.players if hasattr(team_data, 'players') else team_data.get('players', [])
            
            # Analyze players in parallel
            player_tasks = []
            for player_data in players:
                player_id = player_data.player_id if hasattr(player_data, 'player_id') else player_data.get('player_id')
                task = self._analyze_single_player(player_id)
                player_tasks.append(task)
            
            player_analyses = await asyncio.gather(*player_tasks, return_exceptions=True)
            
            # Filter successful analyses
            successful_analyses = []
            for i, analysis in enumerate(player_analyses):
                if isinstance(analysis, Exception):
                    logger.warning(f"Player analysis failed for player {i}: {analysis}")
                    continue
                if analysis:
                    successful_analyses.append(analysis)
            
            # Calculate team metrics
            team_metrics = self._calculate_team_metrics(successful_analyses)
            
            # Analyze team map performance
            team_map_stats = self._analyze_team_maps(successful_analyses)
            
            return {
                "team_name": team_name,
                "player_count": len(successful_analyses),
                "players": successful_analyses,
                "metrics": team_metrics,
                "map_stats": team_map_stats,
                "strong_maps": self._get_strong_maps(team_map_stats),
                "weak_maps": self._get_weak_maps(team_map_stats)
            }
            
        except Exception as e:
            logger.error(f"Error analyzing team {team_name}: {e}")
            raise
    
    async def _analyze_single_player(self, player_id: str) -> Optional[Dict[str, Any]]:
        """Analyze a single player."""
        try:
            # Get player data
            player = await self.cached_api.get_player_by_id(player_id)
            if not player:
                return None
            
            # Get player match history with stats
            matches_with_stats = await self.cached_api.get_matches_with_stats(player_id, limit=50)
            
            # Calculate player metrics
            player_metrics = self._calculate_player_metrics(matches_with_stats, player_id)
            
            # Analyze playstyle
            playstyle = WeaponAnalyzer.analyze_player_playstyle(matches_with_stats, player_id)
            
            # Analyze map performance
            map_stats = MapAnalyzer.analyze_player_maps(matches_with_stats, player_id)
            
            # Calculate danger level
            danger_level = self._calculate_danger_level(player_metrics)
            
            return {
                "player": {
                    "player_id": player.player_id,
                    "nickname": player.nickname,
                    "avatar": player.avatar,
                    "country": player.country,
                    "skill_level": player.games.get('cs2', {}).skill_level if player.games.get('cs2') else 0,
                    "faceit_elo": player.games.get('cs2', {}).faceit_elo if player.games.get('cs2') else 0
                },
                "metrics": player_metrics,
                "playstyle": playstyle,
                "map_stats": map_stats,
                "danger_level": danger_level
            }
            
        except Exception as e:
            logger.warning(f"Error analyzing player {player_id}: {e}")
            return None
    
    def _calculate_player_metrics(self, matches_with_stats: List[Tuple], player_id: str) -> Dict[str, Any]:
        """Calculate player performance metrics."""
        if not matches_with_stats:
            return self._get_empty_metrics()
        
        finished_matches = [
            (match, stats) for match, stats in matches_with_stats 
            if match.status.upper() == "FINISHED"
        ]
        
        if not finished_matches:
            return self._get_empty_metrics()
        
        # Calculate basic stats
        total_matches = len(finished_matches)
        wins = 0
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        total_adr = 0.0
        recent_form = []
        
        for match, stats in finished_matches[:20]:  # Last 20 matches
            # Determine if win
            player_faction = MessageFormatter._get_player_faction(match, player_id)
            is_win = player_faction == match.results.winner if match.results else False
            wins += 1 if is_win else 0
            recent_form.append("W" if is_win else "L")
            
            # Get player stats
            if stats:
                player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
                if player_stats:
                    stats_dict = player_stats.player_stats
                    total_kills += int(stats_dict.get('Kills', '0'))
                    total_deaths += int(stats_dict.get('Deaths', '0'))
                    total_assists += int(stats_dict.get('Assists', '0'))
                    total_adr += float(stats_dict.get('ADR', '0'))
        
        # Calculate metrics
        winrate = round((wins / total_matches) * 100, 1) if total_matches > 0 else 0
        avg_kd = round(total_kills / max(total_deaths, 1), 2)
        avg_adr = round(total_adr / total_matches, 1) if total_matches > 0 else 0
        
        # Calculate HLTV rating
        hltv_rating = MessageFormatter._calculate_hltv_rating_from_stats(
            finished_matches[:30], player_id
        )
        
        return {
            "total_matches": total_matches,
            "winrate": winrate,
            "avg_kd": avg_kd,
            "avg_adr": avg_adr,
            "hltv_rating": hltv_rating,
            "recent_form": "".join(recent_form[:10]),
            "total_kills": total_kills,
            "total_deaths": total_deaths,
            "total_assists": total_assists
        }
    
    def _get_empty_metrics(self) -> Dict[str, Any]:
        """Get empty metrics structure."""
        return {
            "total_matches": 0,
            "winrate": 0.0,
            "avg_kd": 0.0,
            "avg_adr": 0.0,
            "hltv_rating": 0.0,
            "recent_form": "",
            "total_kills": 0,
            "total_deaths": 0,
            "total_assists": 0
        }
    
    def _calculate_team_metrics(self, player_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate team-wide metrics from player analyses."""
        if not player_analyses:
            return {
                "avg_elo": 0,
                "avg_skill_level": 0,
                "team_winrate": 0.0,
                "team_kd": 0.0,
                "team_hltv_rating": 0.0
            }
        
        total_elo = 0
        total_skill_level = 0
        total_winrate = 0.0
        total_kd = 0.0
        total_hltv_rating = 0.0
        
        for analysis in player_analyses:
            player_info = analysis.get("player", {})
            metrics = analysis.get("metrics", {})
            
            total_elo += player_info.get("faceit_elo", 0)
            total_skill_level += player_info.get("skill_level", 0)
            total_winrate += metrics.get("winrate", 0)
            total_kd += metrics.get("avg_kd", 0)
            total_hltv_rating += metrics.get("hltv_rating", 0)
        
        player_count = len(player_analyses)
        
        return {
            "avg_elo": round(total_elo / player_count),
            "avg_skill_level": round(total_skill_level / player_count, 1),
            "team_winrate": round(total_winrate / player_count, 1),
            "team_kd": round(total_kd / player_count, 2),
            "team_hltv_rating": round(total_hltv_rating / player_count, 2)
        }
    
    def _analyze_team_maps(self, player_analyses: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Analyze team performance on different maps."""
        team_map_stats = {}
        
        for analysis in player_analyses:
            player_map_stats = analysis.get("map_stats", {})
            
            for map_name, map_data in player_map_stats.items():
                if map_name not in team_map_stats:
                    team_map_stats[map_name] = {
                        "total_matches": 0,
                        "total_wins": 0,
                        "total_kd": 0.0,
                        "player_count": 0
                    }
                
                team_stats = team_map_stats[map_name]
                team_stats["total_matches"] += map_data.get("matches", 0)
                team_stats["total_wins"] += int(
                    (map_data.get("winrate", 0) / 100) * map_data.get("matches", 0)
                )
                team_stats["total_kd"] += map_data.get("avg_kd", 0)
                team_stats["player_count"] += 1
        
        # Calculate team averages
        for map_name, stats in team_map_stats.items():
            if stats["player_count"] > 0 and stats["total_matches"] > 0:
                stats["avg_winrate"] = round(
                    (stats["total_wins"] / stats["total_matches"]) * 100, 1
                )
                stats["avg_kd"] = round(stats["total_kd"] / stats["player_count"], 2)
            else:
                stats["avg_winrate"] = 0.0
                stats["avg_kd"] = 0.0
        
        return team_map_stats
    
    def _get_strong_maps(self, map_stats: Dict[str, Dict[str, Any]]) -> List[str]:
        """Get team's strong maps."""
        strong_maps = []
        for map_name, stats in map_stats.items():
            if (stats.get("total_matches", 0) >= 5 and 
                stats.get("avg_winrate", 0) >= 65):
                strong_maps.append(map_name)
        return strong_maps
    
    def _get_weak_maps(self, map_stats: Dict[str, Dict[str, Any]]) -> List[str]:
        """Get team's weak maps."""
        weak_maps = []
        for map_name, stats in map_stats.items():
            if (stats.get("total_matches", 0) >= 5 and 
                stats.get("avg_winrate", 0) <= 40):
                weak_maps.append(map_name)
        return weak_maps
    
    def _calculate_danger_level(self, metrics: Dict[str, Any]) -> int:
        """Calculate player danger level (1-5 scale)."""
        score = 0
        
        # HLTV Rating impact (max 2 points)
        hltv_rating = metrics.get("hltv_rating", 0)
        if hltv_rating >= 1.3:
            score += 2
        elif hltv_rating >= 1.1:
            score += 1
        elif hltv_rating >= 1.0:
            score += 0.5
        
        # Winrate impact (max 1.5 points)
        winrate = metrics.get("winrate", 0)
        if winrate >= 70:
            score += 1.5
        elif winrate >= 60:
            score += 1
        elif winrate >= 50:
            score += 0.5
        
        # K/D impact (max 1 point)
        avg_kd = metrics.get("avg_kd", 0)
        if avg_kd >= 1.3:
            score += 1
        elif avg_kd >= 1.1:
            score += 0.5
        
        # Recent form impact (max 0.5 points)
        recent_form = metrics.get("recent_form", "")
        if recent_form:
            recent_wins = recent_form[:5].count('W')
            if recent_wins >= 4:
                score += 0.5
            elif recent_wins >= 3:
                score += 0.3
        
        # Convert to 1-5 scale
        return min(5, max(1, int(score) + 1))
    
    def _generate_match_insights(
        self, 
        team_analyses: Dict[str, Any], 
        match: FaceitMatch
    ) -> Dict[str, Any]:
        """Generate match insights and predictions."""
        team1_data = team_analyses.get("team1", {})
        team2_data = team_analyses.get("team2", {})
        
        insights = {
            "match_prediction": self._predict_match_outcome(team1_data, team2_data),
            "dangerous_players": self._find_dangerous_players(team1_data, team2_data),
            "weak_targets": self._find_weak_targets(team1_data, team2_data),
            "tactical_recommendations": self._generate_tactical_recommendations(team1_data, team2_data),
            "map_recommendations": self._generate_map_recommendations(team1_data, team2_data)
        }
        
        return insights
    
    def _predict_match_outcome(
        self, 
        team1_data: Dict[str, Any], 
        team2_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Predict match outcome based on team metrics."""
        team1_metrics = team1_data.get("metrics", {})
        team2_metrics = team2_data.get("metrics", {})
        
        # Calculate prediction scores
        team1_score = (
            (team1_metrics.get("avg_elo", 0) / 3000) * 30 +
            (team1_metrics.get("team_winrate", 0) / 100) * 25 +
            (team1_metrics.get("team_hltv_rating", 0) / 2) * 25 +
            (team1_metrics.get("team_kd", 0) / 2) * 20
        )
        
        team2_score = (
            (team2_metrics.get("avg_elo", 0) / 3000) * 30 +
            (team2_metrics.get("team_winrate", 0) / 100) * 25 +
            (team2_metrics.get("team_hltv_rating", 0) / 2) * 25 +
            (team2_metrics.get("team_kd", 0) / 2) * 20
        )
        
        total_score = team1_score + team2_score
        if total_score > 0:
            team1_probability = round((team1_score / total_score) * 100, 1)
            team2_probability = round((team2_score / total_score) * 100, 1)
        else:
            team1_probability = team2_probability = 50.0
        
        # Determine favored team
        if abs(team1_probability - team2_probability) < 5:
            prediction = "Even match"
            confidence = "Low"
        else:
            favored_team = team1_data.get("team_name", "Team1") if team1_probability > team2_probability else team2_data.get("team_name", "Team2")
            prediction = f"{favored_team} favored"
            confidence = "High" if abs(team1_probability - team2_probability) > 15 else "Medium"
        
        return {
            "prediction": prediction,
            "confidence": confidence,
            "team1_probability": team1_probability,
            "team2_probability": team2_probability,
            "elo_difference": abs(team1_metrics.get("avg_elo", 0) - team2_metrics.get("avg_elo", 0))
        }
    
    def _find_dangerous_players(
        self, 
        team1_data: Dict[str, Any], 
        team2_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find most dangerous players in the match."""
        all_players = []
        
        for team_data in [team1_data, team2_data]:
            for player_analysis in team_data.get("players", []):
                danger_level = player_analysis.get("danger_level", 1)
                if danger_level >= 4:
                    player_info = player_analysis.get("player", {})
                    metrics = player_analysis.get("metrics", {})
                    
                    all_players.append({
                        "nickname": player_info.get("nickname", "Unknown"),
                        "team": team_data.get("team_name", "Unknown"),
                        "danger_level": danger_level,
                        "hltv_rating": metrics.get("hltv_rating", 0),
                        "winrate": metrics.get("winrate", 0),
                        "avg_kd": metrics.get("avg_kd", 0)
                    })
        
        # Sort by danger level and HLTV rating
        all_players.sort(key=lambda x: (x["danger_level"], x["hltv_rating"]), reverse=True)
        
        return all_players[:3]  # Top 3 most dangerous
    
    def _find_weak_targets(
        self, 
        team1_data: Dict[str, Any], 
        team2_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find weakest players to target."""
        all_players = []
        
        for team_data in [team1_data, team2_data]:
            for player_analysis in team_data.get("players", []):
                danger_level = player_analysis.get("danger_level", 1)
                if danger_level <= 2:
                    player_info = player_analysis.get("player", {})
                    metrics = player_analysis.get("metrics", {})
                    
                    all_players.append({
                        "nickname": player_info.get("nickname", "Unknown"),
                        "team": team_data.get("team_name", "Unknown"),
                        "danger_level": danger_level,
                        "hltv_rating": metrics.get("hltv_rating", 0),
                        "winrate": metrics.get("winrate", 0),
                        "avg_kd": metrics.get("avg_kd", 0)
                    })
        
        # Sort by danger level (ascending) and HLTV rating (ascending)
        all_players.sort(key=lambda x: (x["danger_level"], x["hltv_rating"]))
        
        return all_players[:2]  # 2 weakest players
    
    def _generate_tactical_recommendations(
        self, 
        team1_data: Dict[str, Any], 
        team2_data: Dict[str, Any]
    ) -> List[str]:
        """Generate tactical recommendations."""
        recommendations = []
        
        dangerous_players = self._find_dangerous_players(team1_data, team2_data)
        weak_targets = self._find_weak_targets(team1_data, team2_data)
        
        if dangerous_players:
            top_threat = dangerous_players[0]
            recommendations.append(
                f"🎯 Focus on {top_threat['nickname']} - top threat with {top_threat['hltv_rating']:.2f} rating"
            )
        
        if weak_targets:
            weak_player = weak_targets[0]
            recommendations.append(
                f"💥 Target {weak_player['nickname']} - weak link with {weak_player['hltv_rating']:.2f} rating"
            )
        
        # Team-specific recommendations
        team1_metrics = team1_data.get("metrics", {})
        team2_metrics = team2_data.get("metrics", {})
        
        elo_diff = team1_metrics.get("avg_elo", 0) - team2_metrics.get("avg_elo", 0)
        if abs(elo_diff) > 100:
            favored_team = team1_data.get("team_name", "Team1") if elo_diff > 0 else team2_data.get("team_name", "Team2")
            recommendations.append(f"⚡ {favored_team} has {abs(elo_diff)} ELO advantage")
        
        return recommendations
    
    def _generate_map_recommendations(
        self, 
        team1_data: Dict[str, Any], 
        team2_data: Dict[str, Any]
    ) -> List[str]:
        """Generate map-specific recommendations."""
        recommendations = []
        
        team1_strong = team1_data.get("strong_maps", [])
        team1_weak = team1_data.get("weak_maps", [])
        team2_strong = team2_data.get("strong_maps", [])
        team2_weak = team2_data.get("weak_maps", [])
        
        # Find common strong/weak maps
        common_strong = set(team1_strong) & set(team2_strong)
        team1_advantage = set(team1_strong) - set(team2_strong)
        team2_advantage = set(team2_strong) - set(team1_strong)
        
        if common_strong:
            recommendations.append(f"🗺️ Competitive maps: {', '.join(list(common_strong)[:3])}")
        
        if team1_advantage:
            team1_name = team1_data.get("team_name", "Team1")
            recommendations.append(f"📈 {team1_name} advantage: {', '.join(list(team1_advantage)[:2])}")
        
        if team2_advantage:
            team2_name = team2_data.get("team_name", "Team2")
            recommendations.append(f"📉 {team2_name} advantage: {', '.join(list(team2_advantage)[:2])}")
        
        return recommendations
    
    def _format_analysis_message(self, analysis_data: Dict[str, Any]) -> str:
        """Format analysis data into a readable message."""
        try:
            return format_match_analysis(analysis_data)
        except Exception as e:
            logger.error(f"Error formatting analysis message: {e}")
            return "❌ Error formatting analysis results"
    
    async def _format_existing_analysis(self, analysis: MatchAnalysis) -> str:
        """Format existing analysis for display."""
        try:
            analysis_data = {
                "success": True,
                "match_info": {
                    "competition_name": analysis.competition_name,
                    "status": analysis.status.value if analysis.status else "unknown"
                },
                "team1_analysis": analysis.team1_analysis,
                "team2_analysis": analysis.team2_analysis,
                "prediction": analysis.match_prediction
            }
            
            return self._format_analysis_message(analysis_data)
            
        except Exception as e:
            logger.error(f"Error formatting existing analysis: {e}")
            return "❌ Error formatting cached analysis"
    
    # Match URL parsing
    def _parse_match_id(self, match_url_or_id: str) -> Optional[str]:
        """Parse match ID from FACEIT URL or return if already an ID."""
        if not match_url_or_id:
            return None
        
        match_url_or_id = match_url_or_id.strip()
        
        # If it's already a match ID (UUID format), return it
        if re.match(r'^[a-f0-9-]{36}$', match_url_or_id):
            return match_url_or_id
        
        # Parse FACEIT URL patterns
        patterns = [
            r'faceit\.com/[^/]+/cs2/room/(?:1-)?([a-f0-9-]{36})',
            r'faceit\.com/[^/]+/cs2/room/([a-f0-9-]+)',
            r'room/([a-f0-9-]{36})',
            r'room/1-([a-f0-9-]{36})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, match_url_or_id, re.IGNORECASE)
            if match:
                match_id = match.group(1)
                # Remove "1-" prefix if present
                if match_id.startswith('1-'):
                    match_id = match_id[2:]
                return match_id
        
        return None
    
    # Match history and management
    async def get_user_match_history(
        self,
        telegram_user_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> ServiceResult[List[Dict[str, Any]]]:
        """
        Get user's match analysis history.
        
        Args:
            telegram_user_id: Telegram user ID
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            ServiceResult with match history
        """
        try:
            # Get user
            user = await self.user_repo.get_by_telegram_id(telegram_user_id)
            if not user:
                return ServiceResult.business_rule_error(
                    f"User with Telegram ID {telegram_user_id} not found",
                    "USER_NOT_FOUND"
                )
            
            # Get match analyses
            analyses = await self.match_repo.get_user_analyses(
                user.id, limit, offset
            )
            
            # Format response
            history = []
            for analysis in analyses:
                history.append({
                    "match_id": analysis.match_id,
                    "competition_name": analysis.competition_name,
                    "map_name": analysis.map_name,
                    "status": analysis.status.value if analysis.status else "unknown",
                    "created_at": analysis.created_at,
                    "processing_time_ms": analysis.processing_time_ms
                })
            
            return ServiceResult.success_result(history)
            
        except Exception as e:
            logger.error(f"Error getting match history: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to get match history: {e}", "HISTORY_ERROR")
            )
    
    async def get_match_statistics(
        self,
        telegram_user_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> ServiceResult[Dict[str, Any]]:
        """
        Get match analysis statistics.
        
        Args:
            telegram_user_id: Optional user ID for user-specific stats
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            ServiceResult with statistics
        """
        try:
            # Get user if specified
            user_id = None
            if telegram_user_id:
                user = await self.user_repo.get_by_telegram_id(telegram_user_id)
                if not user:
                    return ServiceResult.business_rule_error(
                        f"User with Telegram ID {telegram_user_id} not found",
                        "USER_NOT_FOUND"
                    )
                user_id = user.id
            
            # Get statistics
            stats = await self.match_repo.get_match_analysis_stats(
                user_id, start_date, end_date
            )
            
            return ServiceResult.success_result(stats)
            
        except Exception as e:
            logger.error(f"Error getting match statistics: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Failed to get match statistics: {e}", "STATISTICS_ERROR")
            )
    
    # Health check implementation
    async def health_check(self) -> ServiceResult[Dict[str, Any]]:
        """Perform match service health check."""
        try:
            health_data = await self._base_health_check()
            
            # Test database connectivity
            try:
                analysis_count = await self.match_repo.count()
                cache_count = await self.match_cache_repo.count()
                health_data["database_status"] = "connected"
                health_data["total_analyses"] = analysis_count
                health_data["cache_entries"] = cache_count
            except Exception as e:
                health_data["database_status"] = f"error: {e}"
                health_data["status"] = "degraded"
            
            # Test FACEIT API connectivity
            try:
                test_match = await self.faceit_api.get_match_details("test-id")
                health_data["faceit_api_status"] = "connected"
            except Exception as e:
                if "not found" in str(e).lower():
                    health_data["faceit_api_status"] = "connected"
                else:
                    health_data["faceit_api_status"] = f"error: {e}"
                    health_data["status"] = "degraded"
            
            return ServiceResult.success_result(health_data)
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return ServiceResult.error_result(
                ServiceError(f"Health check failed: {e}", "HEALTH_CHECK_ERROR")
            )
    
    def __del__(self):
        """Cleanup thread pool on destruction."""
        try:
            if hasattr(self, 'thread_pool'):
                self.thread_pool.shutdown(wait=False)
        except Exception:
            pass