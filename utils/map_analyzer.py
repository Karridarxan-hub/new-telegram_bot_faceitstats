"""Map and weapon analysis utilities."""

import logging
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

from faceit.models import PlayerMatchHistory, MatchStatsResponse
from faceit.api import FaceitAPI
from utils.formatter import MessageFormatter

logger = logging.getLogger(__name__)


class MapAnalyzer:
    """Analyzes player and team performance on specific maps."""
    
    # CS2 competitive map pool
    MAP_POOL = {
        'de_mirage': 'Mirage',
        'de_inferno': 'Inferno', 
        'de_dust2': 'Dust2',
        'de_vertigo': 'Vertigo',
        'de_nuke': 'Nuke',
        'de_overpass': 'Overpass',
        'de_ancient': 'Ancient',
        'de_anubis': 'Anubis'
    }
    
    @staticmethod
    def analyze_player_maps(matches_with_stats: List[Tuple], player_id: str) -> Dict[str, Any]:
        """Analyze player performance on different maps."""
        map_stats = defaultdict(lambda: {
            'matches': 0,
            'wins': 0,
            'kills': 0,
            'deaths': 0,
            'assists': 0,
            'adr': 0.0,
            'rating': 0.0
        })
        
        for match, stats in matches_with_stats:
            if match.status.upper() != "FINISHED" or not stats:
                continue
                
            # Get map name from match
            map_name = MapAnalyzer._extract_map_name(match, stats)
            if not map_name:
                continue
                
            # Get player stats
            player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
            if not player_stats:
                continue
                
            stats_dict = player_stats.player_stats
            
            # Update map statistics
            map_data = map_stats[map_name]
            map_data['matches'] += 1
            
            # Check if win
            player_faction = MessageFormatter._get_player_faction(match, player_id)
            if player_faction == match.results.winner:
                map_data['wins'] += 1
                
            # Add performance stats
            map_data['kills'] += int(stats_dict.get('Kills', '0'))
            map_data['deaths'] += int(stats_dict.get('Deaths', '0'))
            map_data['assists'] += int(stats_dict.get('Assists', '0'))
            map_data['adr'] += float(stats_dict.get('ADR', '0'))
        
        # Calculate averages and percentages
        analyzed_maps = {}
        for map_name, data in map_stats.items():
            if data['matches'] >= 2:  # Only analyze maps with 2+ matches
                analyzed_maps[map_name] = {
                    'matches': data['matches'],
                    'winrate': round((data['wins'] / data['matches']) * 100, 1),
                    'avg_kd': round(data['kills'] / max(data['deaths'], 1), 2),
                    'avg_adr': round(data['adr'] / data['matches'], 1),
                    'total_kills': data['kills'],
                    'total_deaths': data['deaths']
                }
        
        return analyzed_maps
    
    @staticmethod
    def _extract_map_name(match: PlayerMatchHistory, stats: MatchStatsResponse) -> Optional[str]:
        """Extract map name from match data."""
        if not stats or not stats.rounds:
            return None
            
        # Try to get map from round stats
        for round_data in stats.rounds:
            if hasattr(round_data, 'round_stats') and round_data.round_stats:
                map_name = getattr(round_data.round_stats, 'Map', None)
                if map_name:
                    return MapAnalyzer._normalize_map_name(map_name)
        
        return None
    
    @staticmethod
    def _normalize_map_name(map_name: str) -> str:
        """Normalize map name to standard format."""
        map_name = map_name.lower().strip()
        
        # Handle common variations
        map_mapping = {
            'mirage': 'de_mirage',
            'inferno': 'de_inferno',
            'dust2': 'de_dust2',
            'dust_2': 'de_dust2',
            'vertigo': 'de_vertigo',
            'nuke': 'de_nuke',
            'overpass': 'de_overpass',
            'ancient': 'de_ancient',
            'anubis': 'de_anubis'
        }
        
        # Check direct mapping
        if map_name in map_mapping:
            return map_mapping[map_name]
            
        # Check if already in correct format
        if map_name in MapAnalyzer.MAP_POOL:
            return map_name
            
        # Try to find partial match
        for key, value in map_mapping.items():
            if key in map_name or map_name in key:
                return value
                
        return map_name  # Return as-is if no mapping found
    
    @staticmethod
    def generate_map_recommendations(team1_maps: Dict[str, Dict], team2_maps: Dict[str, Dict]) -> List[str]:
        """Generate map pick/ban recommendations based on team performance."""
        recommendations = []
        
        # Find team strengths and weaknesses
        team1_strong = []
        team1_weak = []
        team2_strong = []
        team2_weak = []
        
        for map_name, stats in team1_maps.items():
            if stats['matches'] >= 3:
                if stats['winrate'] >= 70:
                    team1_strong.append((map_name, stats['winrate']))
                elif stats['winrate'] <= 40:
                    team1_weak.append((map_name, stats['winrate']))
        
        for map_name, stats in team2_maps.items():
            if stats['matches'] >= 3:
                if stats['winrate'] >= 70:
                    team2_strong.append((map_name, stats['winrate']))
                elif stats['winrate'] <= 40:
                    team2_weak.append((map_name, stats['winrate']))
        
        # Sort by winrate
        team1_strong.sort(key=lambda x: x[1], reverse=True)
        team1_weak.sort(key=lambda x: x[1])
        team2_strong.sort(key=lambda x: x[1], reverse=True)
        team2_weak.sort(key=lambda x: x[1])
        
        # Generate recommendations
        if team2_weak:
            map_name = MapAnalyzer.MAP_POOL.get(team2_weak[0][0], team2_weak[0][0])
            recommendations.append(f"🎯 Играть: {map_name} (у противника {team2_weak[0][1]}% винрейт)")
        
        if team2_strong:
            map_name = MapAnalyzer.MAP_POOL.get(team2_strong[0][0], team2_strong[0][0])
            recommendations.append(f"❌ Банить: {map_name} (у противника {team2_strong[0][1]}% винрейт)")
        
        if team1_strong:
            map_name = MapAnalyzer.MAP_POOL.get(team1_strong[0][0], team1_strong[0][0])
            recommendations.append(f"✅ Ваша сила: {map_name} ({team1_strong[0][1]}% винрейт)")
        
        return recommendations


class WeaponAnalyzer:
    """Analyzes weapon preferences and playstyles."""
    
    @staticmethod
    def analyze_player_playstyle(matches_with_stats: List[Tuple], player_id: str) -> Dict[str, Any]:
        """Analyze player playstyle and weapon preferences."""
        playstyle_data = {
            'role': 'Rifler',
            'aggression_level': 'Medium',
            'positioning': 'Flexible',
            'weapon_preferences': {},
            'strengths': [],
            'weaknesses': []
        }
        
        if not matches_with_stats:
            return playstyle_data
        
        # Analyze performance metrics
        total_matches = 0
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        total_headshots = 0
        total_adr = 0.0
        high_kill_rounds = 0
        clutch_situations = 0
        entry_frags = 0
        
        for match, stats in matches_with_stats[:30]:  # Last 30 matches
            if match.status.upper() != "FINISHED" or not stats:
                continue
                
            player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
            if not player_stats:
                continue
                
            stats_dict = player_stats.player_stats
            total_matches += 1
            
            kills = int(stats_dict.get('Kills', '0'))
            deaths = int(stats_dict.get('Deaths', '0'))
            assists = int(stats_dict.get('Assists', '0'))
            headshots = int(stats_dict.get('Headshots', '0'))
            adr = float(stats_dict.get('ADR', '0'))
            
            total_kills += kills
            total_deaths += deaths
            total_assists += assists
            total_headshots += headshots
            total_adr += adr
            
            # Estimate rounds in match
            faction1_score = match.results.score.get('faction1', 0)
            faction2_score = match.results.score.get('faction2', 0)
            rounds_played = faction1_score + faction2_score or 24
            
            # High kill performance (indicates aggressive/entry style)
            if kills >= rounds_played * 0.8:
                high_kill_rounds += 1
                
            # Estimate entry frags (players with high kill rounds often entry)
            if kills >= rounds_played * 0.7 and deaths >= rounds_played * 0.6:
                entry_frags += 1
                
            # Clutch estimation
            kd_ratio = kills / max(deaths, 1)
            if kd_ratio > 1.2 and abs(faction1_score - faction2_score) <= 4:
                clutch_situations += 1
        
        if total_matches == 0:
            return playstyle_data
        
        # Calculate averages
        avg_kd = total_kills / max(total_deaths, 1)
        avg_adr = total_adr / total_matches
        avg_hs_rate = (total_headshots / max(total_kills, 1)) * 100
        
        # Determine role based on statistics
        role = WeaponAnalyzer._determine_role(
            avg_kd, avg_adr, avg_hs_rate, high_kill_rounds, total_matches, entry_frags
        )
        
        # Determine aggression level
        aggression = WeaponAnalyzer._determine_aggression(
            avg_kd, avg_adr, high_kill_rounds, total_matches, entry_frags
        )
        
        # Determine positioning style
        positioning = WeaponAnalyzer._determine_positioning(
            avg_kd, avg_adr, clutch_situations, total_matches
        )
        
        playstyle_data.update({
            'role': role,
            'aggression_level': aggression,
            'positioning': positioning,
            'avg_kd': round(avg_kd, 2),
            'avg_adr': round(avg_adr, 1),
            'avg_hs_rate': round(avg_hs_rate, 1),
            'strengths': WeaponAnalyzer._identify_strengths(avg_kd, avg_adr, avg_hs_rate, clutch_situations),
            'weaknesses': WeaponAnalyzer._identify_weaknesses(avg_kd, avg_adr, avg_hs_rate)
        })
        
        return playstyle_data
    
    @staticmethod
    def _determine_role(avg_kd: float, avg_adr: float, avg_hs_rate: float, 
                       high_kill_rounds: int, total_matches: int, entry_frags: int) -> str:
        """Determine player role based on performance patterns."""
        high_kill_ratio = high_kill_rounds / max(total_matches, 1)
        entry_ratio = entry_frags / max(total_matches, 1)
        
        if avg_hs_rate > 50 and avg_kd > 1.3:
            return "AWPer/Sniper"
        elif entry_ratio > 0.4 and avg_kd > 1.0:
            return "Entry Fragger"
        elif high_kill_ratio > 0.3 and avg_adr > 75:
            return "Star Player"
        elif avg_kd < 0.9 and avg_adr > 60:
            return "Support"
        elif avg_kd > 1.1:
            return "Rifler"
        else:
            return "Flex Player"
    
    @staticmethod
    def _determine_aggression(avg_kd: float, avg_adr: float, high_kill_rounds: int, 
                            total_matches: int, entry_frags: int) -> str:
        """Determine aggression level."""
        high_kill_ratio = high_kill_rounds / max(total_matches, 1)
        entry_ratio = entry_frags / max(total_matches, 1)
        
        if entry_ratio > 0.4 or high_kill_ratio > 0.4:
            return "Aggressive"
        elif avg_kd > 1.2 and avg_adr < 70:
            return "Passive"
        else:
            return "Balanced"
    
    @staticmethod
    def _determine_positioning(avg_kd: float, avg_adr: float, clutch_situations: int, 
                             total_matches: int) -> str:
        """Determine positioning style."""
        clutch_ratio = clutch_situations / max(total_matches, 1)
        
        if clutch_ratio > 0.3:
            return "Lurker/Clutch"
        elif avg_adr > 80:
            return "Aggressive angles"
        elif avg_kd > 1.2 and avg_adr < 75:
            return "Safe positions"
        else:
            return "Flexible"
    
    @staticmethod
    def _identify_strengths(avg_kd: float, avg_adr: float, avg_hs_rate: float, 
                          clutch_situations: int) -> List[str]:
        """Identify player strengths."""
        strengths = []
        
        if avg_kd > 1.3:
            strengths.append("Отличный фраггер")
        if avg_adr > 80:
            strengths.append("Высокий урон")
        if avg_hs_rate > 50:
            strengths.append("Точная стрельба")
        if clutch_situations > 5:
            strengths.append("Хорош в клатчах")
        if avg_kd > 1.1 and avg_adr > 70:
            strengths.append("Стабильная игра")
            
        return strengths or ["Командный игрок"]
    
    @staticmethod
    def _identify_weaknesses(avg_kd: float, avg_adr: float, avg_hs_rate: float) -> List[str]:
        """Identify potential weaknesses."""
        weaknesses = []
        
        if avg_kd < 0.9:
            weaknesses.append("Низкий K/D")
        if avg_adr < 60:
            weaknesses.append("Мало урона")
        if avg_hs_rate < 35:
            weaknesses.append("Низкая точность")
        if avg_kd < 0.8 and avg_adr < 55:
            weaknesses.append("Слабое звено")
            
        return weaknesses


def format_map_analysis(player_maps: Dict[str, Dict], player_nickname: str) -> str:
    """Format map analysis into readable message."""
    if not player_maps:
        return f"📊 Недостаточно данных о картах для {player_nickname}"
    
    message = f"🗺️ <b>Анализ карт: {player_nickname}</b>\n\n"
    
    # Sort maps by winrate (best first)
    sorted_maps = sorted(player_maps.items(), key=lambda x: x[1]['winrate'], reverse=True)
    
    strong_maps = []
    weak_maps = []
    
    for map_name, stats in sorted_maps:
        display_name = MapAnalyzer.MAP_POOL.get(map_name, map_name.replace('de_', '').title())
        
        if stats['winrate'] >= 60:
            strong_maps.append((display_name, stats))
        elif stats['winrate'] <= 40:
            weak_maps.append((display_name, stats))
    
    # Strong maps
    if strong_maps:
        message += "✅ <b>Сильные карты:</b>\n"
        for map_name, stats in strong_maps[:3]:
            message += f"• <b>{map_name}</b>: {stats['winrate']}% WR ({stats['matches']} игр) | {stats['avg_kd']} K/D\n"
        message += "\n"
    
    # Weak maps
    if weak_maps:
        message += "❌ <b>Слабые карты:</b>\n"
        for map_name, stats in weak_maps[:3]:
            message += f"• <b>{map_name}</b>: {stats['winrate']}% WR ({stats['matches']} игр) | {stats['avg_kd']} K/D\n"
        message += "\n"
    
    # All maps summary
    message += "📋 <b>Все карты:</b>\n"
    for map_name, stats in sorted_maps:
        display_name = MapAnalyzer.MAP_POOL.get(map_name, map_name.replace('de_', '').title())
        emoji = "🟢" if stats['winrate'] >= 60 else "🔴" if stats['winrate'] <= 40 else "🟡"
        message += f"{emoji} {display_name}: {stats['winrate']}% ({stats['matches']})\n"
    
    return message


def format_playstyle_analysis(playstyle: Dict[str, Any], player_nickname: str) -> str:
    """Format playstyle analysis into readable message."""
    message = f"🎯 <b>Анализ стиля игры: {player_nickname}</b>\n\n"
    
    # Role and style
    message += f"👤 <b>Роль:</b> {playstyle['role']}\n"
    message += f"⚔️ <b>Агрессивность:</b> {playstyle['aggression_level']}\n"
    message += f"📍 <b>Позиционирование:</b> {playstyle['positioning']}\n\n"
    
    # Key stats
    message += f"📊 <b>Ключевые показатели:</b>\n"
    message += f"• K/D: {playstyle.get('avg_kd', 'N/A')}\n"
    message += f"• ADR: {playstyle.get('avg_adr', 'N/A')}\n"
    message += f"• HS%: {playstyle.get('avg_hs_rate', 'N/A')}%\n\n"
    
    # Strengths
    if playstyle['strengths']:
        message += f"💪 <b>Сильные стороны:</b>\n"
        for strength in playstyle['strengths']:
            message += f"• {strength}\n"
        message += "\n"
    
    # Weaknesses
    if playstyle['weaknesses']:
        message += f"⚠️ <b>Слабые места:</b>\n"
        for weakness in playstyle['weaknesses']:
            message += f"• {weakness}\n"
    
    return message