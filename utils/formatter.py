"""Message formatting utilities."""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from faceit.models import (
    PlayerMatchHistory, 
    MatchStatsResponse, 
    FaceitPlayer,
    PlayerStats
)

logger = logging.getLogger(__name__)


class MessageFormatter:
    """Format messages for Telegram bot."""
    
    @staticmethod
    def format_match_result(
        match: PlayerMatchHistory, 
        stats: Optional[MatchStatsResponse], 
        player_id: str
    ) -> str:
        """Format detailed match result message."""
        # Determine if player won
        player_faction = MessageFormatter._get_player_faction(match, player_id)
        is_winner = match.results.winner == player_faction
        result_icon = "🏆" if is_winner else "❌"
        result_text = "ПОБЕДА" if is_winner else "ПОРАЖЕНИЕ"
        
        # Format date
        match_date = datetime.fromtimestamp(match.finished_at).strftime("%d.%m.%Y %H:%M")
        
        # Get map name and score
        map_name = "Неизвестная карта"
        score_text = f"{match.results.score.get('faction1', 0)}:{match.results.score.get('faction2', 0)}"
        
        if stats and stats.rounds:
            map_name = stats.rounds[0].round_stats.Map
        
        # Build message
        message = f"{result_icon} **{result_text}**\\n\\n"
        message += f"🗓 {match_date}\\n"
        message += f"🗺 {map_name}\\n"
        message += f"⚔️ {score_text}\\n"
        message += f"🏟 {match.competition_name}\\n"
        message += f"🔗 [Ссылка на матч]({match.faceit_url})\\n\\n"
        
        # Add player statistics
        if stats and stats.rounds:
            player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
            if player_stats:
                message += "**📊 Твоя статистика:**\\n"
                stats_dict = player_stats.player_stats
                
                message += f"🎯 K/D: {stats_dict.get('Kills', '0')}/{stats_dict.get('Deaths', '0')} ({stats_dict.get('K/D Ratio', '0.00')})\\n"
                message += f"🎪 Assists: {stats_dict.get('Assists', '0')}\\n"
                message += f"💥 ADR: {stats_dict.get('ADR', '0')}\\n"
                message += f"🎯 Headshots: {stats_dict.get('Headshots', '0')} ({stats_dict.get('Headshots %', '0')}%)\\n"
                message += f"⭐ MVP: {stats_dict.get('MVPs', '0')}\\n"
                
                # Multi-kills
                if int(stats_dict.get('Triple Kills', '0')) > 0:
                    message += f"🔥 Triple kills: {stats_dict.get('Triple Kills')}\\n"
                if int(stats_dict.get('Quadro Kills', '0')) > 0:
                    message += f"🚀 Quadro kills: {stats_dict.get('Quadro Kills')}\\n"
                if int(stats_dict.get('Penta Kills', '0')) > 0:
                    message += f"💫 Penta kills: {stats_dict.get('Penta Kills')}\\n"
            
            # Add team statistics
            message += "\\n**👥 Командная статистика:**\\n"
            for i, team in enumerate(stats.rounds[0].teams):
                team_name = f"Команда {i + 1}"
                team_score = team.team_stats.get('Final Score', '0')
                message += f"\\n**{team_name}** ({team_score}):\\n"
                
                for player in team.players:
                    kills = player.player_stats.get('Kills', '0')
                    deaths = player.player_stats.get('Deaths', '0')
                    adr = player.player_stats.get('ADR', '0')
                    message += f"• {player.nickname}: {kills}/{deaths} (ADR: {adr})\\n"
        
        return message
    
    @staticmethod
    def format_matches_list(
        matches: List[PlayerMatchHistory], 
        player_id: str
    ) -> str:
        """Format matches list message."""
        if not matches:
            return "Матчи не найдены."
        
        message = f"**📋 Последние {len(matches)} матчей:**\\n\\n"
        
        for i, match in enumerate(matches):
            player_faction = MessageFormatter._get_player_faction(match, player_id)
            is_winner = match.results.winner == player_faction
            result_icon = "🏆" if is_winner else "❌"
            
            match_date = datetime.fromtimestamp(match.finished_at).strftime("%d.%m")
            score_text = f"{match.results.score.get('faction1', 0)}:{match.results.score.get('faction2', 0)}"
            
            message += f"{i + 1}. {result_icon} {score_text} | {match_date}\\n"
            message += f"   🏟 {match.competition_name}\\n"
            message += f"   🔗 [Детали]({match.faceit_url})\\n\\n"
        
        return message
    
    @staticmethod
    def format_player_info(player: FaceitPlayer) -> str:
        """Format player information message."""
        message = "**👤 Информация об игроке**\\n\\n"
        message += f"🎮 Nickname: {player.nickname}\\n"
        message += f"🌍 Country: {player.country}\\n"
        
        cs2_stats = player.games.get("cs2")
        if cs2_stats:
            message += f"⭐ Skill Level: {cs2_stats.skill_level} ({cs2_stats.skill_level_label})\\n"
            message += f"🏆 Faceit Elo: {cs2_stats.faceit_elo}\\n"
            message += f"🌏 Region: {cs2_stats.region}\\n"
        
        return message
    
    @staticmethod
    def _get_player_faction(match: PlayerMatchHistory, player_id: str) -> str:
        """Get player faction in match."""
        if any(p.player_id == player_id for p in match.teams["faction1"].players):
            return "faction1"
        return "faction2"
    
    @staticmethod
    def _get_player_stats_from_match(
        stats: MatchStatsResponse, 
        player_id: str
    ) -> Optional[PlayerStats]:
        """Get player statistics from match stats."""
        for round_data in stats.rounds:
            for team in round_data.teams:
                for player in team.players:
                    if player.player_id == player_id:
                        return player
        return None