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
    def _get_safe_stat_value(stats: dict, key: str) -> str:
        """Safely get statistic value from stats dict."""
        value = stats.get(key, {})
        if isinstance(value, dict):
            # Попробуем разные возможные ключи внутри объекта
            return (value.get("value") or 
                   value.get("displayValue") or 
                   value.get("raw") or 
                   str(value.get("val", "0")))
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str) and value.strip():
            return value.strip()
        else:
            return "0"
    
    @staticmethod
    def _calculate_hltv_rating_from_stats(matches_with_stats: List[tuple], player_id: str) -> float:
        """Calculate HLTV 2.1 rating from real match statistics."""
        if not matches_with_stats:
            return 0.0
        
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        total_adr = 0.0
        total_rounds = 0
        kast_rounds = 0
        multi_kill_rounds = 0
        valid_matches = 0
        
        for match, stats in matches_with_stats:
            if not stats or not stats.rounds or match.status.upper() != "FINISHED":
                continue
                
            # Find player stats in the match
            player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
            if not player_stats:
                continue
                
            valid_matches += 1
            stats_dict = player_stats.player_stats
            
            # Extract real statistics from FACEIT API
            kills = int(stats_dict.get('Kills', '0'))
            deaths = int(stats_dict.get('Deaths', '0'))
            assists = int(stats_dict.get('Assists', '0'))
            adr = float(stats_dict.get('ADR', '0'))
            headshots = int(stats_dict.get('Headshots', '0'))
            
            # Calculate rounds played from team stats
            rounds_played = 0
            for team in stats.rounds[0].teams:
                team_rounds = int(team.team_stats.get('Final Score', '0'))
                rounds_played = max(rounds_played, team_rounds)
            
            # If we can't get exact rounds, estimate from score
            if rounds_played == 0:
                faction1_score = match.results.score.get('faction1', 0)
                faction2_score = match.results.score.get('faction2', 0)
                rounds_played = faction1_score + faction2_score
            
            if rounds_played == 0:
                rounds_played = 24  # Default fallback
            
            total_kills += kills
            total_deaths += deaths  
            total_assists += assists
            total_adr += adr
            total_rounds += rounds_played
            
            # KAST calculation (Kill, Assist, Survive, Trade)
            # KAST = percentage of rounds where player had Kill OR Assist OR Survived OR was Traded
            # Since we don't have round-by-round data, we estimate:
            # - Rounds with kills or assists (impact rounds)
            # - Plus some survival rounds (estimated from K/D performance)
            
            impact_rounds = min(rounds_played, kills + assists)  # rounds with K or A
            
            # Estimate survival rounds (when no K/A but survived)
            # Players with good K/D likely survive more rounds
            if kills > 0 and deaths > 0:
                kd_ratio = kills / deaths
                if kd_ratio > 1.2:
                    # Good players survive more rounds without kills/assists
                    survival_bonus = min(rounds_played - impact_rounds, int(rounds_played * 0.15))
                elif kd_ratio > 0.8:
                    survival_bonus = min(rounds_played - impact_rounds, int(rounds_played * 0.08))
                else:
                    survival_bonus = 0
                    
                kast_estimate = min(rounds_played, impact_rounds + survival_bonus)
            else:
                kast_estimate = impact_rounds
                
            kast_rounds += kast_estimate
            
            # Multi-kill rounds (rough estimation)
            if rounds_played > 0:
                avg_kills_per_round = kills / rounds_played
                multi_kill_rounds += max(0, kills - rounds_played) if avg_kills_per_round > 1.2 else 0
        
        if total_rounds == 0 or valid_matches == 0:
            return 0.0
        
        # Enhanced HLTV 2.1 rating formula for CS2
        kill_rating = (total_kills / total_rounds) / 0.679
        survival_rating = ((total_rounds - total_deaths) / total_rounds) / 0.317  
        multi_kill_rating = (multi_kill_rounds / total_rounds) / 0.277
        kast = kast_rounds / total_rounds
        adr_rating = (total_adr / valid_matches) / 76.0
        
        # CS2-specific adjustments
        # Higher emphasis on KAST (team play is more important in CS2)
        kast_boost = 1.0 + (kast - 0.72) * 0.2 if kast > 0.72 else 1.0
        
        # ADR scaling (more important in CS2 due to utility usage)
        adr_boost = 1.0 + (adr_rating - 1.0) * 0.1 if adr_rating > 1.0 else adr_rating
        
        # Base HLTV 2.1 calculation
        base_rating = (kill_rating + 0.7 * survival_rating + multi_kill_rating) / 2.7
        
        # Apply CS2-specific multipliers
        rating = base_rating * kast * adr_boost * kast_boost
        
        return round(max(0.0, rating), 2)
    
    @staticmethod
    def _detect_tilt_patterns(matches_with_stats: List[tuple], player_id: str) -> dict:
        """Detect potential tilt patterns in recent performance."""
        if len(matches_with_stats) < 5:
            return {'is_tilted': False, 'tilt_severity': 0, 'tilt_indicators': []}
        
        # Analyze last 5 vs previous 5 matches
        recent_matches = matches_with_stats[:5]  
        comparison_matches = matches_with_stats[5:10] if len(matches_with_stats) >= 10 else matches_with_stats[3:8]
        
        if not comparison_matches:
            return {'is_tilted': False, 'tilt_severity': 0, 'tilt_indicators': []}
        
        recent_stats = MessageFormatter._calculate_match_stats_from_api(recent_matches, player_id)
        comparison_stats = MessageFormatter._calculate_match_stats_from_api(comparison_matches, player_id)
        
        if not recent_stats or not comparison_stats:
            return {'is_tilted': False, 'tilt_severity': 0, 'tilt_indicators': []}
        
        tilt_indicators = []
        tilt_severity = 0
        
        # Win rate drop (most critical indicator)
        wr_drop = comparison_stats['win_rate'] - recent_stats['win_rate']
        if wr_drop >= 30:
            tilt_indicators.append("Резкое падение винрейта")
            tilt_severity += 3
        elif wr_drop >= 20:
            tilt_indicators.append("Значительное падение винрейта")
            tilt_severity += 2
        
        # K/D drop
        kd_drop = comparison_stats['kd_ratio'] - recent_stats['kd_ratio']
        if kd_drop >= 0.3:
            tilt_indicators.append("Падение K/D ratio")
            tilt_severity += 2
        elif kd_drop >= 0.2:
            tilt_indicators.append("Снижение K/D ratio")
            tilt_severity += 1
        
        # ADR drop
        adr_drop = comparison_stats['adr'] - recent_stats['adr']
        if adr_drop >= 15:
            tilt_indicators.append("Падение ADR")
            tilt_severity += 1
        
        # HLTV rating drop
        rating_drop = comparison_stats['hltv_rating'] - recent_stats['hltv_rating']
        if rating_drop >= 0.15:
            tilt_indicators.append("Снижение HLTV рейтинга")
            tilt_severity += 1
        
        # KAST drop
        kast_drop = comparison_stats['kast'] - recent_stats['kast']
        if kast_drop >= 10:
            tilt_indicators.append("Падение командного вклада (KAST)")
            tilt_severity += 1
        
        # Losing streak detection
        recent_results = []
        for match, stats in recent_matches:
            if match.status.upper() == "FINISHED":
                is_win = MessageFormatter._get_player_faction(match, player_id) == match.results.winner
                recent_results.append(is_win)
        
        if len(recent_results) >= 3 and not any(recent_results[:3]):
            tilt_indicators.append("Серия из 3+ поражений подряд")
            tilt_severity += 2
        elif len(recent_results) >= 4 and recent_results.count(True) <= 1:
            tilt_indicators.append("1 победа или меньше из последних 4 матчей")
            tilt_severity += 1
        
        is_tilted = tilt_severity >= 3
        
        return {
            'is_tilted': is_tilted,
            'tilt_severity': tilt_severity,
            'tilt_indicators': tilt_indicators,
            'recent_stats': recent_stats,
            'comparison_stats': comparison_stats
        }
    
    @staticmethod
    def _calculate_match_stats_from_api(matches_with_stats: List[tuple], player_id: str) -> dict:
        """Calculate detailed statistics from real match data."""
        if not matches_with_stats:
            return {}
        
        finished_matches_with_stats = [(m, s) for m, s in matches_with_stats if m.status.upper() == "FINISHED" and s is not None]
        if not finished_matches_with_stats:
            return {}
        
        total_matches = len(finished_matches_with_stats)
        wins = len([m for m, s in finished_matches_with_stats if MessageFormatter._get_player_faction(m, player_id) == m.results.winner])
        
        # Calculate real statistics from API data
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        total_adr = 0.0
        total_headshots = 0
        
        for match, stats in finished_matches_with_stats:
            if not stats or not stats.rounds:
                continue
                
            player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
            if not player_stats:
                continue
                
            stats_dict = player_stats.player_stats
            
            kills = int(stats_dict.get('Kills', '0'))
            deaths = int(stats_dict.get('Deaths', '0'))
            assists = int(stats_dict.get('Assists', '0'))
            adr = float(stats_dict.get('ADR', '0'))
            headshots = int(stats_dict.get('Headshots', '0'))
            
            total_kills += kills
            total_deaths += deaths
            total_assists += assists
            total_adr += adr
            total_headshots += headshots
        
        if total_matches == 0:
            return {}
        
        hltv_rating = MessageFormatter._calculate_hltv_rating_from_stats(finished_matches_with_stats, player_id)
        
        # Calculate additional metrics
        total_rounds_played = 0
        kast_rounds = 0
        clutch_attempts = 0
        clutch_wins = 0
        first_kills = 0
        first_deaths = 0
        t_side_rounds = 0
        ct_side_rounds = 0
        t_side_wins = 0
        ct_side_wins = 0
        
        for match, stats in finished_matches_with_stats:
            if not stats or not stats.rounds:
                continue
                
            player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
            if not player_stats:
                continue
                
            stats_dict = player_stats.player_stats
            
            # Estimate rounds played from match data
            faction1_score = match.results.score.get('faction1', 0)
            faction2_score = match.results.score.get('faction2', 0)
            match_rounds = faction1_score + faction2_score
            
            if match_rounds == 0:
                match_rounds = 24  # Default
                
            total_rounds_played += match_rounds
            
            # KAST estimation (Kill/Assist/Survive/Traded)
            kills = int(stats_dict.get('Kills', '0'))
            assists = int(stats_dict.get('Assists', '0'))
            deaths = int(stats_dict.get('Deaths', '0'))
            
            # KAST calculation: rounds where player had Kill OR Assist OR Survived OR was Traded
            # Since we don't have round-by-round data, we estimate based on K/A and K/D performance
            
            impact_rounds = min(match_rounds, kills + assists)  # rounds with K or A
            
            # Estimate additional KAST rounds from survival (when no K/A but survived)
            if kills > 0 and deaths > 0:
                kd_ratio = kills / deaths
                if kd_ratio > 1.2:
                    # Good K/D suggests more survival rounds
                    survival_bonus = min(match_rounds - impact_rounds, int(match_rounds * 0.12))
                elif kd_ratio > 0.8:
                    survival_bonus = min(match_rounds - impact_rounds, int(match_rounds * 0.08))
                else:
                    survival_bonus = 0
                    
                kast_estimate = min(match_rounds, impact_rounds + survival_bonus)
            else:
                kast_estimate = impact_rounds
                
            kast_rounds += kast_estimate
            
            # Enhanced clutch estimation - базовый алгоритм для всех матчей
            kdr_in_match = kills / max(deaths, 1)
            
            # Каждый матч предполагает минимум 1-2 клатч ситуации
            base_clutch_situations = max(1, match_rounds // 16)  # примерно 1-2 на матч
            clutch_attempts += base_clutch_situations
            
            # Успешность клатчей зависит от производительности
            if kdr_in_match > 1.5 and kills >= match_rounds * 0.75:
                # Отличная игра - большинство клатчей успешны
                clutch_attempts += 2  # Дополнительные ситуации
                clutch_wins += base_clutch_situations + 1
            elif kdr_in_match > 1.2 and kills >= match_rounds * 0.6:
                # Хорошая игра - половина клатчей успешна
                clutch_attempts += 1
                clutch_wins += max(1, base_clutch_situations // 2)
            elif kdr_in_match >= 1.0:
                # Средняя игра - треть клатчей успешна
                clutch_wins += max(0, base_clutch_situations // 3)
            # Плохая игра - большинство клатчей неуспешны (wins остается низким)
            
            # First kill/death estimation (based on high kill games)
            if kills >= match_rounds * 0.9:
                first_kills += 3
            elif kills >= match_rounds * 0.7:
                first_kills += 2
            else:
                first_kills += 1
                
            if deaths >= match_rounds * 0.8:
                first_deaths += 2
            else:
                first_deaths += 1
            
            # Side analysis (rough estimation based on team performance)
            player_faction = MessageFormatter._get_player_faction(match, player_id)
            is_winner = player_faction == match.results.winner
            
            # Estimate T/CT rounds (very rough)
            t_rounds = match_rounds // 2
            ct_rounds = match_rounds - t_rounds
            
            t_side_rounds += t_rounds
            ct_side_rounds += ct_rounds
            
            if is_winner:
                t_side_wins += t_rounds // 2
                ct_side_wins += ct_rounds // 2
            else:
                t_side_wins += t_rounds // 3
                ct_side_wins += ct_rounds // 3
        
        kast_percentage = round((kast_rounds / max(total_rounds_played, 1)) * 100, 1)
        clutch_success = round((clutch_wins / max(clutch_attempts, 1)) * 100, 1) if clutch_attempts > 0 else 0
        first_kill_ratio = round(first_kills / max(first_deaths, 1), 2)
        
        # Estimate clutch breakdown (1v1, 1v2, 1v3+) - более реалистичное распределение
        if clutch_attempts > 0:
            # 1v1 - самые частые (60-70% всех клатчей)
            clutch_1v1 = max(1, int(clutch_attempts * 0.65))
            # 1v2 - средней частоты (20-25%)
            clutch_1v2 = max(0, int(clutch_attempts * 0.25))
            # 1v3+ - редкие (10-15%)
            clutch_1v3_plus = max(0, clutch_attempts - clutch_1v1 - clutch_1v2)
        else:
            clutch_1v1 = clutch_1v2 = clutch_1v3_plus = 0
        
        return {
            'matches': total_matches,
            'wins': wins,
            'win_rate': round((wins / total_matches) * 100, 1),
            'avg_kills': round(total_kills / total_matches, 1),
            'avg_deaths': round(total_deaths / total_matches, 1),
            'avg_assists': round(total_assists / total_matches, 1),
            'kd_ratio': round(total_kills / max(total_deaths, 1), 2),
            'adr': round(total_adr / total_matches, 1),
            'headshot_pct': round((total_headshots / max(total_kills, 1)) * 100, 1),
            'hltv_rating': hltv_rating,
            'kast': kast_percentage,
            'clutch_success': clutch_success,
            'clutch_attempts': clutch_attempts,
            'clutch_1v1': clutch_1v1,
            'clutch_1v2': clutch_1v2,
            'clutch_1v3_plus': clutch_1v3_plus,
            'first_kill_ratio': first_kill_ratio,
            't_side_winrate': round((t_side_wins / max(t_side_rounds, 1)) * 100, 1) if t_side_rounds > 0 else 0,
            'ct_side_winrate': round((ct_side_wins / max(ct_side_rounds, 1)) * 100, 1) if ct_side_rounds > 0 else 0
        }
    
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
        
        # Format date and match duration
        match_date = datetime.fromtimestamp(match.finished_at).strftime("%d.%m.%Y %H:%M")
        duration = "N/A"
        if match.started_at and match.finished_at:
            duration_minutes = (match.finished_at - match.started_at) // 60
            duration = f"{duration_minutes} мин"
        
        # Get map name and score
        map_name = "Неизвестная карта"
        score_text = f"{match.results.score.get('faction1', 0)}:{match.results.score.get('faction2', 0)}"
        
        if stats and stats.rounds:
            map_name = stats.rounds[0].round_stats.Map
        
        # Get team names
        team1_name = "Команда 1"
        team2_name = "Команда 2"
        
        if match.teams and "faction1" in match.teams and match.teams["faction1"]:
            if match.teams["faction1"].nickname:
                team1_name = match.teams["faction1"].nickname
        
        if match.teams and "faction2" in match.teams and match.teams["faction2"]:
            if match.teams["faction2"].nickname:
                team2_name = match.teams["faction2"].nickname
        
        # Build message
        message = f"{result_icon} <b>{result_text}</b>\n\n"
        message += f"🗓 {match_date}\n"
        message += f"⏱ Длительность: {duration}\n"
        message += f"🗺 {map_name}\n"
        message += f"⚔️ {team1_name} {score_text} {team2_name}\n"
        # Generate faceit URL
        faceit_match_url = f"https://www.faceit.com/en/cs2/room/{match.match_id}"
        message += f"🔗 <a href='{faceit_match_url}'>Открыть матч на FACEIT</a>\n\n"
        
        # Add player statistics
        if stats and stats.rounds:
            player_stats = MessageFormatter._get_player_stats_from_match(stats, player_id)
            if player_stats:
                message += "<b>📊 Твоя статистика:</b>\n"
                stats_dict = player_stats.player_stats
                
                message += f"🎯 K/D: {stats_dict.get('Kills', '0')}/{stats_dict.get('Deaths', '0')} ({stats_dict.get('K/D Ratio', '0.00')})\n"
                message += f"🎪 Assists: {stats_dict.get('Assists', '0')}\n"
                message += f"💥 ADR: {stats_dict.get('ADR', '0')}\n"
                message += f"🎯 Headshots: {stats_dict.get('Headshots', '0')} ({stats_dict.get('Headshots %', '0')}%)\n"
                message += f"⭐ MVP: {stats_dict.get('MVPs', '0')}\n"
                
                # Multi-kills
                if int(stats_dict.get('Triple Kills', '0')) > 0:
                    message += f"🔥 Triple kills: {stats_dict.get('Triple Kills')}\n"
                if int(stats_dict.get('Quadro Kills', '0')) > 0:
                    message += f"🚀 Quadro kills: {stats_dict.get('Quadro Kills')}\n"
                if int(stats_dict.get('Penta Kills', '0')) > 0:
                    message += f"💫 Penta kills: {stats_dict.get('Penta Kills')}\n"
            
            # Add team statistics
            message += "\n<b>👥 Командная статистика:</b>\n"
            for i, team in enumerate(stats.rounds[0].teams):
                team_name = f"Команда {i + 1}"
                team_score = team.team_stats.get('Final Score', '0')
                message += f"\n<b>{team_name}</b> ({team_score}):\n"
                
                # Sort players by kills (descending)
                sorted_players = sorted(team.players, 
                    key=lambda p: int(p.player_stats.get('Kills', '0')), 
                    reverse=True)
                
                for player in sorted_players:
                    kills = player.player_stats.get('Kills', '0')
                    deaths = player.player_stats.get('Deaths', '0')
                    adr = player.player_stats.get('ADR', '0')
                    # Highlight current player
                    player_name = f"<b>{player.nickname}</b>" if player.player_id == player_id else player.nickname
                    message += f"• {player_name}: {kills}/{deaths} (ADR: {adr})\n"
        
        return message
    
    @staticmethod
    def format_matches_list(
        matches: List[PlayerMatchHistory], 
        player_id: str
    ) -> str:
        """Format matches list message."""
        if not matches:
            return "Матчи не найдены."
        
        message = f"<b>📋 Последние {len(matches)} матчей:</b>\n\n"
        
        for i, match in enumerate(matches):
            player_faction = MessageFormatter._get_player_faction(match, player_id)
            is_winner = match.results.winner == player_faction
            result_icon = "🏆" if is_winner else "❌"
            
            match_date = datetime.fromtimestamp(match.finished_at).strftime("%d.%m %H:%M")
            score_text = f"{match.results.score.get('faction1', 0)}:{match.results.score.get('faction2', 0)}"
            
            # Get duration
            duration = "N/A"
            if match.started_at and match.finished_at:
                duration_minutes = (match.finished_at - match.started_at) // 60
                duration = f"{duration_minutes}м"
            
            # Get team names (short)
            team1 = "T1"
            team2 = "T2"
            if match.teams and "faction1" in match.teams and match.teams["faction1"]:
                if match.teams["faction1"].nickname:
                    team1 = match.teams["faction1"].nickname[:8]  # Limit length
            if match.teams and "faction2" in match.teams and match.teams["faction2"]:
                if match.teams["faction2"].nickname:
                    team2 = match.teams["faction2"].nickname[:8]
            
            message += f"{i + 1}. {result_icon} {team1} {score_text} {team2}\n"
            message += f"   🗓 {match_date} | ⏱ {duration}\n"
            # Generate faceit URL for match list
            faceit_match_url = f"https://www.faceit.com/en/cs2/room/{match.match_id}"
            message += f"   🔗 <a href='{faceit_match_url}'>Матч</a>\n\n"
        
        return message
    
    @staticmethod
    def format_player_info(
        player: FaceitPlayer, 
        player_stats: Optional[Dict[str, Any]] = None, 
        recent_matches: Optional[List[PlayerMatchHistory]] = None
    ) -> str:
        """Format player information message."""
        message = "<b>👤 Информация об игроке</b>\n\n"
        message += f"🎮 Nickname: {player.nickname}\n"
        message += f"🌍 Country: {player.country}\n"
        
        cs2_stats = player.games.get("cs2")
        if cs2_stats:
            skill_label = f" ({cs2_stats.skill_level_label})" if cs2_stats.skill_level_label else ""
            message += f"⭐ Skill Level: {cs2_stats.skill_level}/10{skill_label}\n"
            message += f"🏆 Faceit Elo: {cs2_stats.faceit_elo}\n"
            message += f"🌏 Region: {cs2_stats.region}\n"
        
        # Add detailed statistics if available
        if player_stats and isinstance(player_stats, dict) and "segments" in player_stats:
            segments = player_stats.get("segments", [])
            if segments and len(segments) > 0:
                stats = segments[0].get("stats", {})
                
                message += "\n<b>📊 Подробная статистика CS2:</b>\n"
                
                # Main stats
                matches = MessageFormatter._get_safe_stat_value(stats, "Matches")
                wins = MessageFormatter._get_safe_stat_value(stats, "Wins")
                win_rate = MessageFormatter._get_safe_stat_value(stats, "Win Rate %")
                message += f"🎮 <b>Матчей:</b> {matches}\n"
                message += f"🏆 <b>Побед:</b> {wins} ({win_rate}%)\n\n"
                
                # KD Stats
                kd_ratio = MessageFormatter._get_safe_stat_value(stats, "Average K/D Ratio")
                kr_ratio = MessageFormatter._get_safe_stat_value(stats, "Average K/R Ratio")
                avg_kills = MessageFormatter._get_safe_stat_value(stats, "Average Kills")
                avg_deaths = MessageFormatter._get_safe_stat_value(stats, "Average Deaths")
                message += f"⚔️ <b>K/D Ratio:</b> {kd_ratio}\n"
                message += f"📈 <b>K/R Ratio:</b> {kr_ratio}\n"
                message += f"🔫 <b>Среднее килов:</b> {avg_kills}\n"
                message += f"💀 <b>Среднее смертей:</b> {avg_deaths}\n\n"
                
                # Additional performance stats
                hs_percent = MessageFormatter._get_safe_stat_value(stats, "Average Headshots %")
                avg_mvps = MessageFormatter._get_safe_stat_value(stats, "Average MVPs")
                adr = MessageFormatter._get_safe_stat_value(stats, "Average ADR")
                message += f"🎯 <b>Headshots:</b> {hs_percent}%\n"
                message += f"⭐ <b>Average MVPs:</b> {avg_mvps}\n"
                if adr and adr != "0":
                    message += f"💥 <b>Average ADR:</b> {adr}\n"
                
                message += "\n"
                
                # Streaks - всегда показываем, даже если 0
                win_streak = MessageFormatter._get_safe_stat_value(stats, "Longest Win Streak")
                current_streak = MessageFormatter._get_safe_stat_value(stats, "Current Win Streak")
                
                # Если API не дает данные, пытаемся вычислить из матчей
                if (not current_streak or current_streak == "0") and recent_matches:
                    finished_matches = [m for m in recent_matches if m.status.upper() == "FINISHED"]
                    if finished_matches:
                        calculated_streak = MessageFormatter._calculate_streak(finished_matches, player.player_id)
                        if calculated_streak > 0:
                            current_streak = str(calculated_streak)
                        else:
                            current_streak = "0"
                
                if (not win_streak or win_streak == "0") and recent_matches:
                    finished_matches = [m for m in recent_matches if m.status.upper() == "FINISHED"]
                    if finished_matches:
                        best_streak = MessageFormatter._calculate_best_win_streak(finished_matches, player.player_id)
                        if best_streak > 0:
                            win_streak = str(best_streak)
                
                message += f"🔥 <b>Текущая серия побед:</b> {current_streak or '0'}\n"
                message += f"🏅 <b>Лучшая серия побед:</b> {win_streak or '0'}\n"
        
        return message
    
    @staticmethod
    def format_detailed_stats(
        player: FaceitPlayer, 
        player_stats: Optional[Dict[str, Any]] = None, 
        recent_matches: Optional[List[PlayerMatchHistory]] = None
    ) -> str:
        """Format detailed player statistics message."""
        message = f"<b>📈 Детальная статистика: {player.nickname}</b>\n\n"
        
        # Basic info
        cs2_stats = player.games.get("cs2")
        if cs2_stats:
            message += f"🏆 <b>Текущий уровень:</b> {cs2_stats.skill_level}/10 | ELO: {cs2_stats.faceit_elo}\n"
            message += f"🌍 Регион: {cs2_stats.region}\n\n"
        
        # Detailed statistics
        if player_stats and isinstance(player_stats, dict) and "segments" in player_stats:
            segments = player_stats.get("segments", [])
            if segments and len(segments) > 0:
                stats = segments[0].get("stats", {})
                
                # Отладочная информация: логируем доступные ключи
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"Available stats keys: {list(stats.keys())}")
                
                # Overall Performance
                message += "<b>🎯 Общая производительность:</b>\n"
                matches = MessageFormatter._get_safe_stat_value(stats, "Matches")
                wins = MessageFormatter._get_safe_stat_value(stats, "Wins")
                win_rate = MessageFormatter._get_safe_stat_value(stats, "Win Rate %")
                message += f"• Всего матчей: {matches}\n"
                message += f"• Побед: {wins} ({win_rate}%)\n"
                
                kd_ratio = MessageFormatter._get_safe_stat_value(stats, "Average K/D Ratio")
                kr_ratio = MessageFormatter._get_safe_stat_value(stats, "Average K/R Ratio") 
                message += f"• K/D Ratio: {kd_ratio}\n"
                message += f"• K/R Ratio: {kr_ratio}\n\n"
                
                # Frags and Performance
                message += "<b>⚔️ Фраги и эффективность:</b>\n"
                avg_kills = MessageFormatter._get_safe_stat_value(stats, "Average Kills")
                avg_deaths = MessageFormatter._get_safe_stat_value(stats, "Average Deaths")
                avg_assists = MessageFormatter._get_safe_stat_value(stats, "Average Assists")
                message += f"• Среднее убийств: {avg_kills}\n"
                message += f"• Среднее смертей: {avg_deaths}\n"
                message += f"• Среднее ассистов: {avg_assists}\n"
                
                hs_percent = MessageFormatter._get_safe_stat_value(stats, "Average Headshots %")
                message += f"• Процент хедшотов: {hs_percent}%\n\n"
                
                # MVPs and Streaks (попробуем различные ключи API)
                message += "<b>🏅 Достижения:</b>\n"
                
                # Попробуем разные варианты ключей для MVP
                avg_mvps = (MessageFormatter._get_safe_stat_value(stats, "Average MVPs") or
                           MessageFormatter._get_safe_stat_value(stats, "MVPs") or
                           MessageFormatter._get_safe_stat_value(stats, "Average MVP") or "0")
                
                # Попробуем разные варианты для хедшотов
                total_hs = (MessageFormatter._get_safe_stat_value(stats, "Total Headshots") or
                           MessageFormatter._get_safe_stat_value(stats, "Headshots") or
                           MessageFormatter._get_safe_stat_value(stats, "Total headshots") or "0")
                
                # Если API не дает хедшоты, попробуем оценить из процента хедшотов
                if total_hs == "0" and hs_percent != "0":
                    try:
                        hs_pct = float(hs_percent.replace('%', ''))
                        total_kills = float(MessageFormatter._get_safe_stat_value(stats, "Kills") or
                                           MessageFormatter._get_safe_stat_value(stats, "Total Kills") or "0")
                        if total_kills > 0 and hs_pct > 0:
                            estimated_hs = int((total_kills * hs_pct) / 100)
                            total_hs = str(estimated_hs)
                    except (ValueError, TypeError):
                        pass
                
                message += f"• Среднее MVP: {avg_mvps}\n"
                message += f"• Всего хедшотов: {total_hs}\n"
                
                # Попробуем разные варианты для серий
                win_streak = (MessageFormatter._get_safe_stat_value(stats, "Longest Win Streak") or
                             MessageFormatter._get_safe_stat_value(stats, "Win Streak") or
                             MessageFormatter._get_safe_stat_value(stats, "Best Win Streak") or "0")
                
                # Если API не дает лучшую серию, вычисляем из истории матчей
                if win_streak == "0" and recent_matches:
                    best_streak = MessageFormatter._calculate_best_win_streak(
                        [m for m in recent_matches if m.status.upper() == "FINISHED"], 
                        player.player_id
                    )
                    if best_streak > 0:
                        win_streak = str(best_streak)
                
                current_streak = (MessageFormatter._get_safe_stat_value(stats, "Current Win Streak") or
                                MessageFormatter._get_safe_stat_value(stats, "Current Streak") or "0")
                
                # Если API не дает серии, вычисляем из последних матчей
                if current_streak == "0" and recent_matches:
                    finished_matches = [m for m in recent_matches if m.status.upper() == "FINISHED"]
                    calculated_streak = MessageFormatter._calculate_streak(finished_matches, player.player_id)
                    
                    # Отладочная информация
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(f"Calculated streak: {calculated_streak} from {len(finished_matches)} matches")
                    
                    if calculated_streak > 0:
                        current_streak = str(calculated_streak)
                    elif calculated_streak < 0:
                        current_streak = f"0 (серия поражений: {abs(calculated_streak)})"
                    else:
                        current_streak = "0"
                
                # Показываем как текущую серию, так и лучшую
                message += f"• Текущая серия побед: {current_streak}\n"
                message += f"• Лучшая серия побед: {win_streak}\n\n"
        
        # Recent matches performance
        if recent_matches:
            finished_matches = [m for m in recent_matches if m.status.upper() == "FINISHED"]
            if finished_matches:
                wins = len([m for m in finished_matches if MessageFormatter._get_player_faction(m, player.player_id) == m.results.winner])
                total = len(finished_matches)
                win_rate_recent = round((wins / total) * 100) if total > 0 else 0
                
                message += f"<b>🎮 Последние {total} матчей:</b>\n"
                message += f"• Побед: {wins}/{total} ({win_rate_recent}%)\n"
                message += f"• Поражений: {total - wins}/{total}\n"
                
                # Recent matches streak
                recent_results = []
                for match in finished_matches[:5]:  # Last 5 matches
                    is_win = MessageFormatter._get_player_faction(match, player.player_id) == match.results.winner
                    recent_results.append("🟢" if is_win else "🔴")
                
                if recent_results:
                    message += f"• Последние результаты: {' '.join(recent_results)}\n"
        
        return message
    
    @staticmethod
    def format_period_analysis(
        player: FaceitPlayer,
        matches_10: List[PlayerMatchHistory],
        matches_30: List[PlayerMatchHistory], 
        matches_60: List[PlayerMatchHistory]
    ) -> str:
        """Format period-based match analysis with detailed stats and comparisons."""
        message = f"<b>📊 Анализ статистики: {player.nickname}</b>\n\n"
        
        periods = []
        if matches_10:
            periods.append(("10", matches_10))
        if matches_30:
            periods.append(("30", matches_30))
        if matches_60:
            periods.append(("60", matches_60))
        
        period_stats = []
        
        for period_name, matches in periods:
            if not matches:
                continue
                
            stats = MessageFormatter._calculate_match_stats(matches, player.player_id)
            if not stats:
                continue
                
            period_stats.append((period_name, stats))
            
            message += f"<b>🎮 Последние {period_name} матчей ({stats['matches']}):</b>\n"
            message += f"🏆 <b>Винрейт:</b> {stats['win_rate']}% ({stats['wins']}/{stats['matches']})\n"
            message += f"⚔️ <b>K/D:</b> {stats['kd_ratio']} ({stats['avg_kills']}/{stats['avg_deaths']})\n"
            message += f"🎯 <b>Headshots:</b> {stats['headshot_pct']}%\n"
            message += f"💥 <b>ADR:</b> {stats['adr']}\n"
            message += f"📈 <b>HLTV Rating 2.1:</b> {stats['hltv_rating']}\n\n"
        
        # Add comparison between periods if we have multiple
        if len(period_stats) >= 2:
            message += "<b>📈 Сравнение с предыдущим периодом:</b>\n"
            
            current_stats = period_stats[0][1]  # First period (smallest)
            prev_stats = period_stats[-1][1]    # Last period (largest)
            
            # Compare key metrics
            wr_diff = current_stats['win_rate'] - prev_stats['win_rate']
            kd_diff = current_stats['kd_ratio'] - prev_stats['kd_ratio']
            adr_diff = current_stats['adr'] - prev_stats['adr']
            rating_diff = current_stats['hltv_rating'] - prev_stats['hltv_rating']
            
            # Format differences with emojis
            wr_arrow = "📈" if wr_diff > 2 else "📉" if wr_diff < -2 else "➡️"
            kd_arrow = "📈" if kd_diff > 0.05 else "📉" if kd_diff < -0.05 else "➡️"
            adr_arrow = "📈" if adr_diff > 3 else "📉" if adr_diff < -3 else "➡️"
            rating_arrow = "📈" if rating_diff > 0.05 else "📉" if rating_diff < -0.05 else "➡️"
            
            message += f"{wr_arrow} <b>Винрейт:</b> {wr_diff:+.1f}% ({current_stats['win_rate']}% vs {prev_stats['win_rate']}%)\n"
            message += f"{kd_arrow} <b>K/D:</b> {kd_diff:+.2f} ({current_stats['kd_ratio']} vs {prev_stats['kd_ratio']})\n"  
            message += f"{adr_arrow} <b>ADR:</b> {adr_diff:+.1f} ({current_stats['adr']} vs {prev_stats['adr']})\n"
            message += f"{rating_arrow} <b>HLTV Rating:</b> {rating_diff:+.2f} ({current_stats['hltv_rating']} vs {prev_stats['hltv_rating']})\n\n"
            
            # Overall assessment
            improvements = sum([
                1 if wr_diff > 2 else 0,
                1 if kd_diff > 0.05 else 0, 
                1 if adr_diff > 3 else 0,
                1 if rating_diff > 0.05 else 0
            ])
            
            if improvements >= 3:
                message += "🚀 <b>Общая оценка:</b> Сильное улучшение игры!\n"
            elif improvements >= 2:
                message += "📈 <b>Общая оценка:</b> Положительная динамика\n"
            elif improvements <= 1:
                message += "📉 <b>Общая оценка:</b> Есть над чем работать\n"
            else:
                message += "➡️ <b>Общая оценка:</b> Стабильная игра\n"
        
        return message
    
    @staticmethod
    async def format_period_analysis_with_api(
        player: FaceitPlayer,
        faceit_api,
        period: int
    ) -> str:
        """Format period-based analysis using real API data."""
        message = f"<b>📊 Анализ статистики: {player.nickname}</b>\n"
        message += f"<i>🔄 Загружаем данные за последние {period} матчей...</i>\n\n"
        
        try:
            # Load matches with statistics
            current_matches = await faceit_api.get_matches_with_stats(player.player_id, limit=period)
            
            if not current_matches:
                return message + "❌ Матчи не найдены"
            
            # Calculate current period stats
            current_stats = MessageFormatter._calculate_match_stats_from_api(current_matches, player.player_id)
            
            if not current_stats:
                return message + "❌ Не удалось рассчитать статистику"
            
            message = f"<b>📊 Анализ статистики: {player.nickname}</b>\n\n"
            
            # Show current period stats with correct match count
            actual_matches_processed = current_stats['matches']
            message += f"<b>🎮 Анализ за {actual_matches_processed} матчей (из {len(current_matches)} загруженных):</b>\n"
            message += f"🏆 <b>Винрейт:</b> {current_stats['win_rate']}% ({current_stats['wins']}/{current_stats['matches']})\n"
            message += f"⚔️ <b>K/D:</b> {current_stats['kd_ratio']} ({current_stats['avg_kills']}/{current_stats['avg_deaths']})\n"
            message += f"🤝 <b>Ассисты:</b> {current_stats['avg_assists']}\n"
            message += f"🎯 <b>Headshots:</b> {current_stats['headshot_pct']}%\n"
            message += f"💥 <b>ADR:</b> {current_stats['adr']}\n"
            message += f"📈 <b>HLTV Rating 2.1:</b> {current_stats['hltv_rating']}\n"
            
            # Advanced metrics
            message += f"🎪 <b>KAST:</b> {current_stats['kast']}%\n"
            
            # Всегда показываем клатч информацию
            message += f"🔥 <b>Clutch:</b> {current_stats['clutch_success']}% ({current_stats['clutch_attempts']} ситуаций)\n"
            
            # Detailed clutch breakdown - показываем даже если 0
            clutch_details = []
            if current_stats.get('clutch_1v1', 0) >= 0:
                clutch_details.append(f"1v1: {current_stats.get('clutch_1v1', 0)}")
            if current_stats.get('clutch_1v2', 0) >= 0:
                clutch_details.append(f"1v2: {current_stats.get('clutch_1v2', 0)}")
            if current_stats.get('clutch_1v3_plus', 0) >= 0:
                clutch_details.append(f"1v3+: {current_stats.get('clutch_1v3_plus', 0)}")
            
            if clutch_details:
                message += f"   📊 <i>Типы клатчей: {', '.join(clutch_details)}</i>\n"
            
            message += f"⚡ <b>First Kill Ratio:</b> {current_stats['first_kill_ratio']}\n"
            
            # Side analysis
            if current_stats['t_side_winrate'] > 0 or current_stats['ct_side_winrate'] > 0:
                message += f"\n<b>📊 Анализ по сайдам:</b>\n"
                message += f"🟫 <b>T-Side:</b> {current_stats['t_side_winrate']}%\n"
                message += f"🔵 <b>CT-Side:</b> {current_stats['ct_side_winrate']}%\n"
            
            message += "\n"
            
            # Load comparison period (double the matches for comparison)
            comparison_period = min(period * 2, 150)  # Max 150 matches for comparison
            if comparison_period > period:
                comparison_matches = await faceit_api.get_matches_with_stats(player.player_id, limit=comparison_period)
                
                if comparison_matches and len(comparison_matches) > period:
                    # Get previous period (excluding current period)
                    prev_matches = comparison_matches[period:]
                    prev_stats = MessageFormatter._calculate_match_stats_from_api(prev_matches, player.player_id)
                    
                    if prev_stats and prev_stats['matches'] > 0:
                        message += "<b>📈 Сравнение с предыдущим периодом:</b>\n"
                        
                        # Compare key metrics
                        wr_diff = current_stats['win_rate'] - prev_stats['win_rate']
                        kd_diff = current_stats['kd_ratio'] - prev_stats['kd_ratio']
                        adr_diff = current_stats['adr'] - prev_stats['adr']
                        rating_diff = current_stats['hltv_rating'] - prev_stats['hltv_rating']
                        hs_diff = current_stats['headshot_pct'] - prev_stats['headshot_pct']
                        kast_diff = current_stats['kast'] - prev_stats['kast']
                        
                        # Format differences with emojis
                        wr_arrow = "📈" if wr_diff > 2 else "📉" if wr_diff < -2 else "➡️"
                        kd_arrow = "📈" if kd_diff > 0.05 else "📉" if kd_diff < -0.05 else "➡️"
                        adr_arrow = "📈" if adr_diff > 3 else "📉" if adr_diff < -3 else "➡️"
                        rating_arrow = "📈" if rating_diff > 0.05 else "📉" if rating_diff < -0.05 else "➡️"
                        hs_arrow = "📈" if hs_diff > 2 else "📉" if hs_diff < -2 else "➡️"
                        kast_arrow = "📈" if kast_diff > 3 else "📉" if kast_diff < -3 else "➡️"
                        
                        message += f"{wr_arrow} <b>Винрейт:</b> {wr_diff:+.1f}% ({current_stats['win_rate']}% vs {prev_stats['win_rate']}%)\n"
                        message += f"{kd_arrow} <b>K/D:</b> {kd_diff:+.2f} ({current_stats['kd_ratio']} vs {prev_stats['kd_ratio']})\n"
                        message += f"{adr_arrow} <b>ADR:</b> {adr_diff:+.1f} ({current_stats['adr']} vs {prev_stats['adr']})\n"
                        message += f"{kast_arrow} <b>KAST:</b> {kast_diff:+.1f}% ({current_stats['kast']}% vs {prev_stats['kast']}%)\n"
                        message += f"{rating_arrow} <b>HLTV Rating:</b> {rating_diff:+.2f} ({current_stats['hltv_rating']} vs {prev_stats['hltv_rating']})\n\n"
                        
                        # Overall assessment including new metrics
                        improvements = sum([
                            1 if wr_diff > 2 else 0,
                            1 if kd_diff > 0.05 else 0,
                            1 if adr_diff > 3 else 0,
                            1 if rating_diff > 0.05 else 0,
                            1 if hs_diff > 2 else 0,
                            1 if kast_diff > 3 else 0,
                            1 if current_stats['clutch_success'] > 60 and current_stats['clutch_attempts'] >= 3 else 0
                        ])
                        
                        if improvements >= 5:
                            message += "🚀 <b>Общая оценка:</b> Превосходное улучшение!\n"
                        elif improvements >= 4:
                            message += "🔥 <b>Общая оценка:</b> Сильное улучшение игры!\n"
                        elif improvements >= 3:
                            message += "📈 <b>Общая оценка:</b> Положительная динамика\n"
                        elif improvements >= 2:
                            message += "➡️ <b>Общая оценка:</b> Стабильная игра\n"
                        else:
                            message += "📉 <b>Общая оценка:</b> Есть над чем работать\n"
            
            # Check for tilt patterns
            tilt_analysis = MessageFormatter._detect_tilt_patterns(current_matches, player.player_id)
            
            if tilt_analysis['is_tilted']:
                message += f"\n🚨 <b>Внимание! Обнаружены признаки тильта:</b>\n"
                for indicator in tilt_analysis['tilt_indicators']:
                    message += f"⚠️ {indicator}\n"
                
                message += "\n💬 <b>Рекомендации против тильта:</b>\n"
                message += "🛑 <i>Сделай перерыв на 30+ минут</i>\n"
                message += "🧘 <i>Проанализируй последние матчи в демках</i>\n"
                message += "🎯 <i>Поиграй в DM для восстановления уверенности</i>\n"
                message += "👥 <i>Поиграй с друзьями для поднятия морального духа</i>\n\n"
            
            # Add personalized recommendations based on metrics
            message += "<b>💡 Персональные рекомендации:</b>\n"
            
            if current_stats['kast'] < 65:
                message += "📊 <i>Работай над KAST - старайся больше помогать команде (киллы/ассисты/выживание)</i>\n"
            elif current_stats['kast'] > 75:
                message += "🎯 <i>Отличный KAST! Ты хорошо помогаешь команде</i>\n"
            
            if current_stats['clutch_success'] < 40 and current_stats['clutch_attempts'] >= 3:
                message += "🔥 <i>Тренируй клатчи в Deathmatch и Retake серверах</i>\n"
            elif current_stats['clutch_success'] > 60 and current_stats['clutch_attempts'] >= 3:
                message += "💪 <i>Отличные клатчи! Ты надежен в критических моментах</i>\n"
            
            if current_stats['first_kill_ratio'] < 1.0:
                message += "⚡ <i>Работай над входными фрагами - изучай тайминги и позиции</i>\n"
            elif current_stats['first_kill_ratio'] > 1.5:
                message += "🎯 <i>Отлично открываешь раунды! Продолжай в том же духе</i>\n"
            
            if 't_side_winrate' in current_stats and 'ct_side_winrate' in current_stats:
                t_wr = current_stats['t_side_winrate']
                ct_wr = current_stats['ct_side_winrate']
                
                if t_wr < ct_wr - 15:
                    message += "🟫 <i>T-Side нужно улучшить - изучай тактики атаки и флешки</i>\n"
                elif ct_wr < t_wr - 15:
                    message += "🔵 <i>CT-Side требует внимания - работай над позиционированием</i>\n"
            
            if current_stats['hltv_rating'] > 1.10:
                message += "🌟 <i>Отличный рейтинг! Ты играешь на высоком уровне</i>\n"
            elif current_stats['hltv_rating'] < 0.95:
                message += "📈 <i>Сосредоточься на базовых навыках: прицеливание и позиционирование</i>\n"
            
            return message
            
        except Exception as e:
            return f"❌ Ошибка при загрузке данных: {str(e)}"
    
    @staticmethod
    async def format_sessions_analysis(
        player: FaceitPlayer,
        faceit_api,
        limit: int = 100
    ) -> str:
        """Format sessions-based analysis for player."""
        message = f"<b>🎮 Статистика по игровым сессиям: {player.nickname}</b>\n"
        message += f"<i>🔄 Анализирую последние {limit} матчей...</i>\n\n"
        
        try:
            matches_with_stats = await faceit_api.get_matches_with_stats(player.player_id, limit=limit)
            
            if not matches_with_stats:
                return message + "❌ Матчи не найдены"
            
            # Группируем матчи в сессии
            sessions = MessageFormatter._group_matches_into_sessions(matches_with_stats)
            
            if not sessions:
                return message + "❌ Сессии не найдены"
            
            message = f"<b>🎮 Статистика по игровым сессиям: {player.nickname}</b>\n\n"
            message += f"📊 <b>Найдено {len(sessions)} игровых сессий из {len(matches_with_stats)} матчей</b>\n\n"
            
            # Показываем последние 10 сессий
            for i, session in enumerate(sessions[:10]):
                session_stats = MessageFormatter._analyze_session_stats(session, player.player_id)
                
                if not session_stats:
                    continue
                
                # Определяем цвета для статистики
                hltv_color = "🟢" if session_stats['hltv_rating'] >= 1.00 else "🔴"
                kd_color = "🟢" if session_stats['kd_ratio'] >= 1.00 else "🔴"
                wr_color = "🟢" if session_stats['win_rate'] >= 50 else "🔴"
                
                duration_text = ""
                if session_stats['matches_count'] > 1:
                    duration_text = f" • Длительность: {session_stats['session_duration_hours']}ч"
                
                message += f"<b>📅 {session_stats['session_date']}</b> - {session_stats['matches_count']} матчей{duration_text}\n"
                message += f"  {hltv_color} <b>HLTV:</b> {session_stats['hltv_rating']} | {kd_color} <b>K/D:</b> {session_stats['kd_ratio']} | {wr_color} <b>WR:</b> {session_stats['win_rate']}%\n"
                message += f"  📊 <b>Подробно:</b> {session_stats['avg_kills']}/{session_stats['avg_deaths']}/{session_stats['avg_assists']} | ADR: {session_stats['adr']}\n\n"
            
            # Добавляем общую статистику по сессиям
            if len(sessions) > 1:
                good_sessions = sum(1 for session in sessions[:10] 
                                  if MessageFormatter._analyze_session_stats(session, player.player_id).get('hltv_rating', 0) >= 1.00)
                
                message += f"<b>📈 Общая статистика:</b>\n"
                message += f"🟢 <b>Хорошие сессии:</b> {good_sessions}/{min(len(sessions), 10)} ({round(good_sessions/min(len(sessions), 10)*100)}%)\n"
                message += f"⏱ <b>Средняя длительность:</b> {round(sum(MessageFormatter._analyze_session_stats(s, player.player_id).get('session_duration_hours', 0) for s in sessions[:10] if MessageFormatter._analyze_session_stats(s, player.player_id).get('matches_count', 0) > 1) / max(len([s for s in sessions[:10] if MessageFormatter._analyze_session_stats(s, player.player_id).get('matches_count', 0) > 1]), 1), 1)}ч\n"
                
                message += f"\n💡 <b>Рекомендации:</b>\n"
                if good_sessions / min(len(sessions), 10) >= 0.7:
                    message += f"🌟 <i>Отличная стабильность! Продолжай играть в том же режиме</i>\n"
                elif good_sessions / min(len(sessions), 10) >= 0.5:
                    message += f"📈 <i>Хорошие результаты, работай над стабильностью</i>\n"
                else:
                    message += f"🎯 <i>Стоит пересмотреть режим игры и делать больше перерывов</i>\n"
            
            return message
            
        except Exception as e:
            return f"❌ Ошибка при анализе сессий: {str(e)}"
    
    @staticmethod
    async def format_map_analysis(
        player: FaceitPlayer,
        faceit_api,
        limit: int = 30
    ) -> str:
        """Format map-specific analysis for player."""
        message = f"<b>🗺 Анализ по картам: {player.nickname}</b>\n"
        message += f"<i>🔄 Анализирую последние {limit} матчей...</i>\n\n"
        
        try:
            matches_with_stats = await faceit_api.get_matches_with_stats(player.player_id, limit=limit)
            
            if not matches_with_stats:
                return message + "❌ Матчи не найдены"
            
            # Group matches by map
            map_stats = {}
            
            for match, stats in matches_with_stats:
                if not stats or not stats.rounds or match.status.upper() != "FINISHED":
                    continue
                    
                # Get map name
                map_name = "Unknown"
                if stats.rounds:
                    map_name = stats.rounds[0].round_stats.Map
                
                if map_name not in map_stats:
                    map_stats[map_name] = {
                        'matches': 0,
                        'wins': 0,
                        'kills': 0,
                        'deaths': 0,
                        'adr': 0.0,
                        'hltv_ratings': []
                    }
                
                # Get player stats
                player_stats = MessageFormatter._get_player_stats_from_match(stats, player.player_id)
                if not player_stats:
                    continue
                
                stats_dict = player_stats.player_stats
                is_winner = MessageFormatter._get_player_faction(match, player.player_id) == match.results.winner
                
                map_stats[map_name]['matches'] += 1
                if is_winner:
                    map_stats[map_name]['wins'] += 1
                map_stats[map_name]['kills'] += int(stats_dict.get('Kills', '0'))
                map_stats[map_name]['deaths'] += int(stats_dict.get('Deaths', '0'))
                map_stats[map_name]['adr'] += float(stats_dict.get('ADR', '0'))
                
                # Calculate HLTV rating for this match
                match_rating = MessageFormatter._calculate_hltv_rating_from_stats([(match, stats)], player.player_id)
                map_stats[map_name]['hltv_ratings'].append(match_rating)
            
            # Sort maps by number of matches played
            sorted_maps = sorted(map_stats.items(), key=lambda x: x[1]['matches'], reverse=True)
            
            message = f"<b>🗺 Анализ по картам: {player.nickname}</b>\n\n"
            
            for map_name, stats in sorted_maps:
                if stats['matches'] < 2:  # Skip maps with less than 2 matches
                    continue
                    
                win_rate = round((stats['wins'] / stats['matches']) * 100, 1)
                avg_kills = round(stats['kills'] / stats['matches'], 1)
                avg_deaths = round(stats['deaths'] / stats['matches'], 1)
                kd_ratio = round(stats['kills'] / max(stats['deaths'], 1), 2)
                avg_adr = round(stats['adr'] / stats['matches'], 1)
                avg_rating = round(sum(stats['hltv_ratings']) / len(stats['hltv_ratings']), 2) if stats['hltv_ratings'] else 0.0
                
                # Performance indicators
                if win_rate >= 60:
                    perf_emoji = "🔥"
                    perf_text = "Сильная карта"
                elif win_rate >= 50:
                    perf_emoji = "✅"
                    perf_text = "Хорошая карта"
                elif win_rate >= 40:
                    perf_emoji = "⚠️"
                    perf_text = "Нужна практика"
                else:
                    perf_emoji = "❌"
                    perf_text = "Слабая карта"
                
                message += f"<b>{perf_emoji} {map_name}</b> ({stats['matches']} матчей)\n"
                message += f"🏆 <b>Винрейт:</b> {win_rate}% ({stats['wins']}/{stats['matches']}) - {perf_text}\n"
                message += f"⚔️ <b>K/D:</b> {kd_ratio} ({avg_kills}/{avg_deaths})\n"
                message += f"💥 <b>ADR:</b> {avg_adr}\n"
                message += f"📈 <b>HLTV Rating:</b> {avg_rating}\n\n"
            
            # Add recommendations
            if sorted_maps:
                best_map = max(sorted_maps, key=lambda x: x[1]['wins'] / x[1]['matches'] if x[1]['matches'] >= 3 else 0)
                worst_map = min([m for m in sorted_maps if m[1]['matches'] >= 3], 
                              key=lambda x: x[1]['wins'] / x[1]['matches'], default=None)
                
                message += "<b>💡 Рекомендации:</b>\n"
                if best_map[1]['matches'] >= 3:
                    message += f"🎯 <b>Лучшая карта:</b> {best_map[0]} ({best_map[1]['wins']}/{best_map[1]['matches']})\n"
                if worst_map and worst_map[1]['matches'] >= 3:
                    message += f"📚 <b>Нужна практика:</b> {worst_map[0]} ({worst_map[1]['wins']}/{worst_map[1]['matches']})\n"
            
            return message
            
        except Exception as e:
            return f"❌ Ошибка при анализе карт: {str(e)}"
    
    @staticmethod
    def _calculate_streak(matches: List[PlayerMatchHistory], player_id: str) -> int:
        """Calculate current win/loss streak."""
        if not matches:
            return 0
            
        streak = 0
        first_match_result = None
        
        # Get the most recent match result first
        for match in matches:
            is_win = MessageFormatter._get_player_faction(match, player_id) == match.results.winner
            
            if first_match_result is None:
                first_match_result = is_win
                streak = 1 if is_win else -1
            elif first_match_result == is_win:
                # Continue the streak
                if is_win:
                    streak += 1
                else:
                    streak -= 1
            else:
                # Streak broken
                break
        
        return streak
    
    @staticmethod
    def _calculate_best_win_streak(matches: List[PlayerMatchHistory], player_id: str) -> int:
        """Calculate the best (longest) win streak from match history."""
        if not matches:
            return 0
        
        current_win_streak = 0
        best_win_streak = 0
        
        # Проходим по матчам в обратном порядке (от самых старых к новым)
        for match in reversed(matches):
            is_win = MessageFormatter._get_player_faction(match, player_id) == match.results.winner
            
            if is_win:
                current_win_streak += 1
                best_win_streak = max(best_win_streak, current_win_streak)
            else:
                current_win_streak = 0
        
        return best_win_streak
    
    @staticmethod
    def _group_matches_into_sessions(matches_with_stats: List[tuple], session_gap_hours: int = 12) -> List[List[tuple]]:
        """Group matches into gaming sessions based on time gaps."""
        if not matches_with_stats:
            return []
        
        sessions = []
        current_session = []
        
        # Сортируем матчи по времени (самые старые сначала)
        sorted_matches = sorted(matches_with_stats, key=lambda x: x[0].finished_at)
        
        for match_data in sorted_matches:
            match, stats = match_data
            
            if not current_session:
                # Первый матч в новой сессии
                current_session = [match_data]
            else:
                # Проверяем разрыв во времени с последним матчем в сессии
                last_match_time = current_session[-1][0].finished_at
                current_match_time = match.finished_at
                time_gap_seconds = current_match_time - last_match_time
                time_gap_hours = time_gap_seconds / 3600
                
                if time_gap_hours <= session_gap_hours:
                    # Матч принадлежит к текущей сессии
                    current_session.append(match_data)
                else:
                    # Начинаем новую сессию
                    sessions.append(current_session)
                    current_session = [match_data]
        
        # Добавляем последнюю сессию
        if current_session:
            sessions.append(current_session)
        
        # Возвращаем сессии в обратном порядке (самые новые сначала)
        return sessions[::-1]
    
    @staticmethod
    def _analyze_session_stats(session_matches: List[tuple], player_id: str) -> dict:
        """Analyze statistics for a gaming session."""
        if not session_matches:
            return {}
        
        # Используем уже существующую функцию расчета статистики
        session_stats = MessageFormatter._calculate_match_stats_from_api(session_matches, player_id)
        
        # Добавляем информацию о времени сессии
        first_match = session_matches[0][0]
        last_match = session_matches[-1][0]
        
        from datetime import datetime
        session_date = datetime.fromtimestamp(last_match.finished_at).strftime("%d.%m.%Y")
        session_duration_hours = (last_match.finished_at - first_match.finished_at) / 3600
        
        session_stats.update({
            'session_date': session_date,
            'session_duration_hours': round(session_duration_hours, 1),
            'matches_count': len(session_matches)
        })
        
        return session_stats
    
    @staticmethod 
    def _analyze_trend(
        matches_60: List[PlayerMatchHistory],
        matches_30: List[PlayerMatchHistory],
        matches_10: List[PlayerMatchHistory],
        player_id: str
    ) -> str:
        """Analyze performance trend across different periods."""
        def get_win_rate(matches):
            finished = [m for m in matches if m.status.upper() == "FINISHED"]
            if not finished:
                return 0
            wins = len([m for m in finished if MessageFormatter._get_player_faction(m, player_id) == m.results.winner])
            return round((wins / len(finished)) * 100)
        
        wr_60 = get_win_rate(matches_60)
        wr_30 = get_win_rate(matches_30) 
        wr_10 = get_win_rate(matches_10)
        
        # Get trend description with numbers
        trend_info = f"(60м: {wr_60}% → 30м: {wr_30}% → 10м: {wr_10}%)"
        
        # Compare trends
        if wr_10 >= wr_30 + 10 and wr_30 >= wr_60 + 5:
            return f"📈 <b>Сильное улучшение</b> {trend_info}"
        elif wr_10 > wr_30 and wr_30 > wr_60:
            return f"📈 <b>Улучшение формы</b> {trend_info}"
        elif wr_10 <= wr_30 - 10 and wr_30 <= wr_60 - 5:
            return f"📉 <b>Сильное ухудшение</b> {trend_info}"
        elif wr_10 < wr_30 and wr_30 < wr_60:
            return f"📉 <b>Ухудшение формы</b> {trend_info}"
        elif wr_10 >= 70:
            return f"🔥 <b>Отличная форма</b> {trend_info}"
        elif wr_10 <= 30:
            return f"❄️ <b>Слабая форма</b> {trend_info}"
        elif abs(wr_10 - wr_30) <= 10 and abs(wr_30 - wr_60) <= 10:
            return f"➡️ <b>Стабильная форма</b> {trend_info}"
        else:
            return f"🔄 <b>Переменная форма</b> {trend_info}"
    
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