"""Match analyzer for pre-game analysis."""

import logging
import re
import asyncio
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta

from faceit.api import FaceitAPI, FaceitAPIError
from faceit.models import FaceitMatch, FaceitPlayer, PlayerMatchHistory, MatchStatsResponse
from utils.formatter import MessageFormatter
from utils.map_analyzer import MapAnalyzer, WeaponAnalyzer
from utils.cache import CachedFaceitAPI

logger = logging.getLogger(__name__)


class PlayerAnalysis:
    """Analysis data for a single player."""
    
    def __init__(self, player: FaceitPlayer):
        self.player = player
        self.recent_matches: List[PlayerMatchHistory] = []
        self.match_stats: List[Tuple[PlayerMatchHistory, Optional[MatchStatsResponse]]] = []
        self.winrate = 0.0
        self.avg_kd = 0.0
        self.avg_adr = 0.0
        self.hltv_rating = 0.0
        self.form_streak = ""  # "WWLWW" etc
        self.preferred_weapons: Dict[str, float] = {}
        self.map_performance: Dict[str, Dict[str, Any]] = {}
        self.clutch_stats = {"attempts": 0, "success": 0, "rate": 0.0}
        self.danger_level = 0  # 1-5 scale
        self.role = "Rifler"  # AWPer, Rifler, Support, Entry
        self.playstyle_data: Dict[str, Any] = {}
        self.map_stats: Dict[str, Any] = {}


class TeamAnalysis:
    """Analysis data for a team."""
    
    def __init__(self, team_name: str):
        self.team_name = team_name
        self.players: List[PlayerAnalysis] = []
        self.avg_elo = 0
        self.avg_level = 0
        self.team_synergy = 0.0
        self.strong_maps: List[str] = []
        self.weak_maps: List[str] = []
        self.team_map_stats: Dict[str, Dict[str, Any]] = {}


class MatchAnalyzer:
    """Analyzes matches and provides pre-game insights."""
    
    def __init__(self, faceit_api: FaceitAPI):
        self.api = faceit_api
        self.cached_api = CachedFaceitAPI(faceit_api)
        
    def parse_faceit_url(self, url: str) -> Optional[str]:
        """Extract match ID from FACEIT URL."""
        # FACEIT URLs can be in different formats:
        # https://www.faceit.com/en/cs2/room/1-abc123-def456-ghi789
        # https://www.faceit.com/en/cs2/room/abc123-def456-ghi789
        # https://faceit.com/en/cs2/room/1-abc123-def456-ghi789
        
        patterns = [
            r'faceit\.com/[^/]+/cs2/room/(?:1-)?([a-f0-9-]{36})',
            r'faceit\.com/[^/]+/cs2/room/([a-f0-9-]+)',
            r'room/([a-f0-9-]{36})',
            r'room/1-([a-f0-9-]{36})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                match_id = match.group(1)
                # Remove "1-" prefix if present
                if match_id.startswith('1-'):
                    match_id = match_id[2:]
                logger.info(f"Extracted match ID: {match_id}")
                return match_id
        
        logger.warning(f"Could not extract match ID from URL: {url}")
        return None
    
    async def analyze_match(self, match_url_or_id: str) -> Dict[str, Any]:
        """Analyze a match and return pre-game insights."""
        try:
            # Parse match ID from URL if needed
            if 'faceit.com' in match_url_or_id:
                match_id = self.parse_faceit_url(match_url_or_id)
                if not match_id:
                    return {"error": "Не удалось извлечь ID матча из ссылки"}
            else:
                match_id = match_url_or_id
            
            # Get match details
            match = await self.api.get_match_details(match_id)
            if not match:
                return {"error": "Матч не найден"}
            
            # Check if match is suitable for analysis
            if match.status and match.status.upper() == "FINISHED":
                return {"error": "Матч уже завершён"}
            
            # Analyze both teams in parallel
            team_analyses = {}
            team_names = list(match.teams.keys())
            
            if len(team_names) != 2:
                return {"error": "Неподдерживаемый формат матча"}
            
            # Параллельный анализ обеих команд
            team_tasks = []
            for team_name in team_names:
                team = match.teams[team_name]
                task = self._analyze_team(team.players, team_name)
                team_tasks.append((team_name, task))
            
            # Выполняем анализ команд параллельно
            team_results = await asyncio.gather(*[task for _, task in team_tasks], return_exceptions=True)
            
            for i, result in enumerate(team_results):
                team_name = team_tasks[i][0]
                if isinstance(result, Exception):
                    logger.error(f"Error analyzing team {team_name}: {result}")
                    return {"error": f"Ошибка анализа команды {team_name}"}
                team_analyses[team_name] = result
            
            # Generate match insights
            insights = self._generate_match_insights(team_analyses, match)
            
            return {
                "success": True,
                "match": match,
                "team_analyses": team_analyses,
                "insights": insights
            }
            
        except FaceitAPIError as e:
            logger.error(f"FACEIT API error in match analysis: {e}")
            return {"error": "Ошибка API FACEIT"}
        except Exception as e:
            logger.error(f"Unexpected error in match analysis: {e}")
            return {"error": f"Неожиданная ошибка: {str(e)}"}
    
    async def _analyze_team(self, players: List, team_name: str) -> TeamAnalysis:
        """Analyze a team and its players."""
        team_analysis = TeamAnalysis(team_name)
        
        total_elo = 0
        total_level = 0
        
        # Параллельный анализ всех игроков команды
        player_tasks = []
        for player_data in players:
            task = self._analyze_single_player(player_data.player_id)
            player_tasks.append(task)
        
        # Выполняем все задачи параллельно
        player_results = await asyncio.gather(*player_tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        for i, result in enumerate(player_results):
            if isinstance(result, Exception):
                logger.warning(f"Error analyzing player {players[i].player_id}: {result}")
                continue
            
            if result is None:
                continue
                
            player_analysis = result
            team_analysis.players.append(player_analysis)
            
            # Add to team totals
            if 'cs2' in player_analysis.player.games:
                total_elo += player_analysis.player.games['cs2'].faceit_elo
                total_level += player_analysis.player.games['cs2'].skill_level
        
        # Calculate team averages
        player_count = len(team_analysis.players)
        if player_count > 0:
            team_analysis.avg_elo = total_elo // player_count
            team_analysis.avg_level = total_level // player_count
        
        # Analyze team map performance
        team_analysis.team_map_stats = self._analyze_team_maps(team_analysis.players)
        team_analysis.strong_maps, team_analysis.weak_maps = self._identify_team_map_preferences(team_analysis.team_map_stats)
        
        return team_analysis
    
    async def _analyze_single_player(self, player_id: str) -> Optional[PlayerAnalysis]:
        """Быстрый анализ одного игрока (для параллельной обработки)."""
        try:
            # Get full player info (используем кэшированный API)
            player = await self.cached_api.get_player_by_id(player_id)
            if not player:
                return None
            
            # Analyze individual player
            return await self._analyze_player(player)
            
        except Exception as e:
            logger.warning(f"Error analyzing player {player_id}: {e}")
            return None
    
    async def _analyze_player(self, player: FaceitPlayer) -> PlayerAnalysis:
        """Analyze individual player."""
        analysis = PlayerAnalysis(player)
        
        try:
            # Get recent matches with stats (используем кэшированный API)
            matches_with_stats = await self.cached_api.get_matches_with_stats(player.player_id, limit=50)
            analysis.match_stats = matches_with_stats
            
            # Filter only finished matches
            finished_matches = [(m, s) for m, s in matches_with_stats if m.status.upper() == "FINISHED"]
            
            if not finished_matches:
                return analysis
            
            # Calculate basic stats
            wins = 0
            total_matches = len(finished_matches)
            total_kills = 0
            total_deaths = 0
            total_adr = 0.0
            recent_results = []
            
            for match, stats in finished_matches[:20]:  # Last 20 matches for form
                # Determine if win
                player_faction = MessageFormatter._get_player_faction(match, player.player_id)
                is_win = player_faction == match.results.winner
                wins += 1 if is_win else 0
                recent_results.append("W" if is_win else "L")
                
                # Get player stats from match
                if stats:
                    player_stats = MessageFormatter._get_player_stats_from_match(stats, player.player_id)
                    if player_stats:
                        stats_dict = player_stats.player_stats
                        total_kills += int(stats_dict.get('Kills', '0'))
                        total_deaths += int(stats_dict.get('Deaths', '0'))
                        total_adr += float(stats_dict.get('ADR', '0'))
            
            # Calculate performance metrics
            analysis.winrate = round((wins / total_matches) * 100, 1) if total_matches > 0 else 0
            analysis.avg_kd = round(total_kills / max(total_deaths, 1), 2)
            analysis.avg_adr = round(total_adr / total_matches, 1) if total_matches > 0 else 0
            analysis.form_streak = "".join(recent_results[:10])  # Last 10 matches
            
            # Calculate HLTV rating using existing formatter
            analysis.hltv_rating = MessageFormatter._calculate_hltv_rating_from_stats(
                finished_matches[:30], player.player_id
            )
            
            # Analyze player role and weapon preferences
            analysis.role, analysis.preferred_weapons = self._analyze_player_role(finished_matches, player.player_id)
            
            # Analyze playstyle using WeaponAnalyzer
            analysis.playstyle_data = WeaponAnalyzer.analyze_player_playstyle(finished_matches, player.player_id)
            
            # Analyze map performance
            analysis.map_stats = MapAnalyzer.analyze_player_maps(finished_matches, player.player_id)
            
            # Calculate danger level (1-5 scale)
            analysis.danger_level = self._calculate_danger_level(analysis)
            
            # Analyze clutch performance
            analysis.clutch_stats = self._analyze_clutch_performance(finished_matches, player.player_id)
            
        except Exception as e:
            logger.warning(f"Error in detailed player analysis for {player.nickname}: {e}")
        
        return analysis
    
    def _analyze_player_role(self, matches_with_stats: List[Tuple], player_id: str) -> Tuple[str, Dict[str, float]]:
        """Analyze player's role and weapon preferences."""
        total_kills = 0
        total_deaths = 0
        headshot_percentage = 0.0
        matches_analyzed = 0
        
        for match, stats in matches_with_stats[:20]:  # Analyze last 20 matches
            if not stats:
                continue
                
            player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
            if not player_stats:
                continue
            
            stats_dict = player_stats.player_stats
            kills = int(stats_dict.get('Kills', '0'))
            deaths = int(stats_dict.get('Deaths', '0'))
            headshots = int(stats_dict.get('Headshots', '0'))
            
            total_kills += kills
            total_deaths += deaths
            if kills > 0:
                headshot_percentage += (headshots / kills) * 100
            matches_analyzed += 1
        
        if matches_analyzed == 0:
            return "Rifler", {}
        
        # Calculate averages
        avg_kd = total_kills / max(total_deaths, 1)
        avg_hs = headshot_percentage / matches_analyzed
        
        # Determine role based on performance patterns
        role = "Rifler"  # Default
        
        if avg_kd > 1.3 and avg_hs > 45:
            role = "AWPer/Sniper"  # High KD + high HS suggests precision shooting
        elif avg_kd > 1.1 and avg_hs > 50:
            role = "Entry Fragger"  # Good KD + very high HS
        elif avg_kd < 0.9:
            role = "Support"  # Lower KD suggests support role
        
        # Simplified weapon preferences (would need more detailed stats from API)
        weapon_prefs = {
            "rifle_preference": 70.0,  # Placeholder - would analyze actual weapon stats
            "awp_preference": 15.0 if "AWP" in role else 5.0,
            "pistol_skill": avg_hs * 0.8  # Estimate based on headshot %
        }
        
        return role, weapon_prefs
    
    def _calculate_danger_level(self, analysis: PlayerAnalysis) -> int:
        """Calculate player danger level (1-5 scale)."""
        score = 0
        
        # HLTV Rating impact (max 2 points)
        if analysis.hltv_rating >= 1.3:
            score += 2
        elif analysis.hltv_rating >= 1.1:
            score += 1
        elif analysis.hltv_rating >= 1.0:
            score += 0.5
        
        # Winrate impact (max 1.5 points)
        if analysis.winrate >= 70:
            score += 1.5
        elif analysis.winrate >= 60:
            score += 1
        elif analysis.winrate >= 50:
            score += 0.5
        
        # K/D impact (max 1 point)
        if analysis.avg_kd >= 1.3:
            score += 1
        elif analysis.avg_kd >= 1.1:
            score += 0.5
        
        # Recent form impact (max 0.5 points)
        recent_wins = analysis.form_streak[:5].count('W')
        if recent_wins >= 4:
            score += 0.5
        elif recent_wins >= 3:
            score += 0.3
        
        # Convert to 1-5 scale
        return min(5, max(1, int(score) + 1))
    
    def _analyze_clutch_performance(self, matches_with_stats: List[Tuple], player_id: str) -> Dict[str, Any]:
        """Analyze clutch performance (simplified)."""
        # This is a simplified version - real clutch analysis would require
        # round-by-round data which might not be available in basic FACEIT API
        
        clutch_attempts = 0
        clutch_success = 0
        
        # Estimate clutch performance based on K/D in tight matches
        for match, stats in matches_with_stats[:30]:
            if not stats or not match.results:
                continue
                
            # Check if it was a close match (good indicator of clutch situations)
            faction1_score = match.results.score.get('faction1', 0)
            faction2_score = match.results.score.get('faction2', 0)
            
            if abs(faction1_score - faction2_score) <= 4:  # Close match
                player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
                if player_stats:
                    stats_dict = player_stats.player_stats
                    kd = int(stats_dict.get('Kills', '0')) / max(int(stats_dict.get('Deaths', '0')), 1)
                    
                    clutch_attempts += 1
                    if kd > 1.0:  # Performed well in close match
                        clutch_success += 1
        
        clutch_rate = (clutch_success / max(clutch_attempts, 1)) * 100
        
        return {
            "attempts": clutch_attempts,
            "success": clutch_success,
            "rate": round(clutch_rate, 1)
        }
    
    def _generate_match_insights(self, team_analyses: Dict[str, TeamAnalysis], match: FaceitMatch) -> Dict[str, Any]:
        """Generate match insights and recommendations."""
        teams = list(team_analyses.values())
        team1, team2 = teams[0], teams[1]
        
        insights = {
            "dangerous_players": [],
            "weak_targets": [],
            "elo_advantage": None,
            "team_recommendations": [],
            "key_matchups": []
        }
        
        # Find dangerous players (danger level 4-5)
        all_players = team1.players + team2.players
        dangerous = [p for p in all_players if p.danger_level >= 4]
        dangerous.sort(key=lambda x: x.danger_level, reverse=True)
        insights["dangerous_players"] = dangerous[:3]  # Top 3 most dangerous
        
        # Find weak targets (danger level 1-2)
        weak_targets = [p for p in all_players if p.danger_level <= 2]
        weak_targets.sort(key=lambda x: x.danger_level)
        insights["weak_targets"] = weak_targets[:2]  # 2 weakest players
        
        # Calculate ELO advantage
        elo_diff = team1.avg_elo - team2.avg_elo
        if abs(elo_diff) > 50:
            favored_team = team1.team_name if elo_diff > 0 else team2.team_name
            insights["elo_advantage"] = {
                "favored_team": favored_team,
                "elo_difference": abs(elo_diff)
            }
        
        # Generate team recommendations
        recommendations = []
        
        if dangerous:
            recommendations.append(f"🎯 Фокус на {dangerous[0].player.nickname} - самый опасный игрок (уровень {dangerous[0].danger_level})")
        
        if weak_targets:
            recommendations.append(f"💥 Атаковать {weak_targets[0].player.nickname} - слабое звено команды")
        
        # AWP analysis
        awpers = [p for p in all_players if "AWP" in p.role]
        if awpers:
            recommendations.append(f"🎯 Внимание на AWP игроков: {', '.join([p.player.nickname for p in awpers])}")
        
        insights["team_recommendations"] = recommendations
        
        return insights
    
    def _analyze_team_maps(self, players: List[PlayerAnalysis]) -> Dict[str, Dict[str, Any]]:
        """Analyze team performance on maps by combining player stats."""
        team_map_stats = {}
        
        for player in players:
            for map_name, map_data in player.map_stats.items():
                if map_name not in team_map_stats:
                    team_map_stats[map_name] = {
                        'total_matches': 0,
                        'total_wins': 0,
                        'total_kd': 0.0,
                        'player_count': 0
                    }
                
                team_stats = team_map_stats[map_name]
                team_stats['total_matches'] += map_data['matches']
                team_stats['total_wins'] += int((map_data['winrate'] / 100) * map_data['matches'])
                team_stats['total_kd'] += map_data['avg_kd']
                team_stats['player_count'] += 1
        
        # Calculate team averages
        for map_name, stats in team_map_stats.items():
            if stats['player_count'] > 0:
                stats['avg_winrate'] = round((stats['total_wins'] / max(stats['total_matches'], 1)) * 100, 1)
                stats['avg_kd'] = round(stats['total_kd'] / stats['player_count'], 2)
        
        return team_map_stats
    
    def _identify_team_map_preferences(self, team_map_stats: Dict[str, Dict[str, Any]]) -> Tuple[List[str], List[str]]:
        """Identify team's strong and weak maps."""
        strong_maps = []
        weak_maps = []
        
        for map_name, stats in team_map_stats.items():
            if stats['total_matches'] >= 6:  # Need sufficient data
                if stats['avg_winrate'] >= 65:
                    strong_maps.append(map_name)
                elif stats['avg_winrate'] <= 40:
                    weak_maps.append(map_name)
        
        return strong_maps, weak_maps


def format_match_analysis(analysis_result: Dict[str, Any]) -> str:
    """Format match analysis into readable message."""
    if not analysis_result.get("success"):
        return f"❌ {analysis_result.get('error', 'Ошибка анализа')}"
    
    match = analysis_result["match"]
    team_analyses = analysis_result["team_analyses"]
    insights = analysis_result["insights"]
    
    teams = list(team_analyses.values())
    team1, team2 = teams[0], teams[1]
    
    message = f"🔍 <b>Анализ матча перед игрой</b>\n\n"
    
    # Match info
    if match.competition_name:
        message += f"🏆 <b>{match.competition_name}</b>\n"
    message += f"⚔️ <b>{team1.team_name}</b> vs <b>{team2.team_name}</b>\n\n"
    
    # ELO comparison
    message += f"📊 <b>Уровень команд:</b>\n"
    message += f"• {team1.team_name}: {team1.avg_elo} ELO (Уровень {team1.avg_level})\n"
    message += f"• {team2.team_name}: {team2.avg_elo} ELO (Уровень {team2.avg_level})\n\n"
    
    # ELO advantage
    if insights.get("elo_advantage"):
        adv = insights["elo_advantage"]
        message += f"⚡ <b>Преимущество:</b> {adv['favored_team']} (+{adv['elo_difference']} ELO)\n\n"
    
    # Dangerous players
    if insights.get("dangerous_players"):
        message += f"💀 <b>ОПАСНЫЕ ИГРОКИ:</b>\n"
        for player in insights["dangerous_players"]:
            p = player.player
            message += f"• <b>{p.nickname}</b> ({player.role}) - {player.hltv_rating:.2f} Rating, {player.winrate}% WR\n"
            message += f"  📈 Форма: {player.form_streak[:5]} | K/D: {player.avg_kd}\n"
        message += "\n"
    
    # Weak targets
    if insights.get("weak_targets"):
        message += f"🎯 <b>СЛАБЫЕ ЦЕЛИ:</b>\n"
        for player in insights["weak_targets"]:
            p = player.player
            message += f"• <b>{p.nickname}</b> - {player.hltv_rating:.2f} Rating, {player.winrate}% WR\n"
        message += "\n"
    
    # Map recommendations
    team1, team2 = teams[0], teams[1]
    if team1.strong_maps or team2.strong_maps or team1.weak_maps or team2.weak_maps:
        message += f"🗺️ <b>АНАЛИЗ КАРТ:</b>\n"
        
        # Map recommendations using MapAnalyzer
        map_recommendations = MapAnalyzer.generate_map_recommendations(
            team1.team_map_stats, team2.team_map_stats
        )
        
        for rec in map_recommendations:
            message += f"• {rec}\n"
        message += "\n"
    
    # Team recommendations
    if insights.get("team_recommendations"):
        message += f"💡 <b>ТАКТИЧЕСКИЕ РЕКОМЕНДАЦИИ:</b>\n"
        for rec in insights["team_recommendations"]:
            message += f"• {rec}\n"
        message += "\n"
    
    # Detailed team analysis
    for team in teams:
        message += f"👥 <b>Команда {team.team_name}:</b>\n"
        team.players.sort(key=lambda x: x.danger_level, reverse=True)
        
        for player in team.players:
            p = player.player
            danger_emoji = ["😴", "😐", "😊", "😤", "💀"][player.danger_level - 1]
            
            # Get playstyle info
            playstyle = player.playstyle_data
            role = playstyle.get('role', player.role)
            aggression = playstyle.get('aggression_level', 'Medium')
            
            message += f"{danger_emoji} <b>{p.nickname}</b> ({role})\n"
            message += f"   📊 {player.hltv_rating:.2f} HLTV | {player.avg_kd} K/D | {player.winrate}% WR\n"
            message += f"   🎮 {player.form_streak[:5]} | 🎪 Clutch: {player.clutch_stats['rate']}%\n"
            message += f"   ⚔️ Стиль: {aggression} | "
            
            # Add strengths if available
            if playstyle.get('strengths'):
                message += f"{playstyle['strengths'][0]}\n"
            else:
                message += f"ADR: {player.avg_adr}\n"
        message += "\n"
    
    message += f"🚀 <b>Удачной игры!</b>"
    
    return message