"""FACEIT API client."""

import logging
import asyncio
from typing import List, Optional, Dict, Any
import aiohttp
from aiohttp import ClientTimeout

from config.settings import settings
from .models import (
    FaceitPlayer, 
    PlayerMatchHistory, 
    FaceitMatch, 
    MatchStatsResponse
)

logger = logging.getLogger(__name__)


class FaceitAPIError(Exception):
    """FACEIT API error."""
    pass


class FaceitAPI:
    """FACEIT API client."""
    
    def __init__(self):
        self.base_url = settings.faceit_api_base_url
        self.api_key = settings.faceit_api_key
        self.timeout = ClientTimeout(total=30)
        
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to FACEIT API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.request(
                    method, 
                    url, 
                    headers=headers, 
                    params=params
                ) as response:
                    if response.status == 404:
                        return None
                    elif response.status >= 400:
                        error_text = await response.text()
                        logger.error(f"FACEIT API error {response.status}: {error_text}")
                        raise FaceitAPIError(f"API request failed: {response.status}")
                    
                    return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error: {e}")
            raise FaceitAPIError(f"Network error: {e}")

    async def search_player(self, nickname: str) -> Optional[FaceitPlayer]:
        """Search player by nickname."""
        logger.info(f"Searching for player: {nickname}")
        
        data = await self._make_request(
            "GET", 
            "/players", 
            params={"nickname": nickname}
        )
        
        if not data:
            logger.info(f"Player not found: {nickname}")
            return None
            
        try:
            return FaceitPlayer(**data)
        except Exception as e:
            logger.error(f"Failed to parse player data: {e}")
            raise FaceitAPIError(f"Failed to parse player data: {e}")

    async def get_player_by_id(self, player_id: str) -> Optional[FaceitPlayer]:
        """Get player by ID."""
        logger.info(f"Getting player by ID: {player_id}")
        
        data = await self._make_request("GET", f"/players/{player_id}")
        
        if not data:
            return None
            
        try:
            return FaceitPlayer(**data)
        except Exception as e:
            logger.error(f"Failed to parse player data: {e}")
            raise FaceitAPIError(f"Failed to parse player data: {e}")

    async def get_player_matches(
        self, 
        player_id: str, 
        limit: int = 20, 
        offset: int = 0,
        game: str = "cs2"
    ) -> List[PlayerMatchHistory]:
        """Get player match history."""
        logger.info(f"Getting matches for player {player_id} (limit: {limit})")
        
        data = await self._make_request(
            "GET", 
            f"/players/{player_id}/history",
            params={
                "game": game,
                "limit": limit,
                "offset": offset
            }
        )
        
        if not data or "items" not in data:
            logger.warning(f"No matches found for player {player_id}")
            return []
            
        try:
            matches = []
            for match_data in data["items"]:
                match = PlayerMatchHistory(**match_data)
                matches.append(match)
            return matches
        except Exception as e:
            logger.error(f"Failed to parse matches data: {e}")
            return []

    async def get_match_details(self, match_id: str) -> Optional[FaceitMatch]:
        """Get match details by ID."""
        logger.info(f"Getting match details: {match_id}")
        
        data = await self._make_request("GET", f"/matches/{match_id}")
        
        if not data:
            return None
            
        try:
            return FaceitMatch(**data)
        except Exception as e:
            logger.error(f"Failed to parse match data: {e}")
            raise FaceitAPIError(f"Failed to parse match data: {e}")

    async def get_match_stats(self, match_id: str) -> Optional[MatchStatsResponse]:
        """Get match statistics."""
        logger.info(f"Getting match stats: {match_id}")
        
        data = await self._make_request("GET", f"/matches/{match_id}/stats")
        
        if not data:
            return None
            
        try:
            return MatchStatsResponse(**data)
        except Exception as e:
            logger.error(f"Failed to parse match stats: {e}")
            raise FaceitAPIError(f"Failed to parse match stats: {e}")

    async def get_player_stats(
        self, 
        player_id: str, 
        game: str = "cs2"
    ) -> Optional[Dict[str, Any]]:
        """Get player statistics."""
        logger.info(f"Getting player stats: {player_id}")
        
        data = await self._make_request("GET", f"/players/{player_id}/stats/{game}")
        return data

    async def check_player_new_matches(
        self, 
        player_id: str, 
        last_checked_match_id: Optional[str] = None
    ) -> List[PlayerMatchHistory]:
        """Check for new matches since last check."""
        logger.info(f"Checking new matches for player {player_id}")
        
        matches = await self.get_player_matches(player_id, limit=5)
        
        if not last_checked_match_id:
            # Return finished matches if no last checked match
            return [match for match in matches if match.status.upper() == "FINISHED"]
        
        new_matches = []
        for match in matches:
            if match.match_id == last_checked_match_id:
                break
            if match.status.upper() == "FINISHED":
                new_matches.append(match)
        
        logger.info(f"Found {len(new_matches)} new matches for player {player_id}")
        return new_matches

    async def get_matches_with_stats(
        self,
        player_id: str,
        limit: int = 20,
        game: str = "cs2"
    ) -> List[tuple]:
        """Get player matches with detailed statistics."""
        logger.info(f"Getting matches with stats for player {player_id} (limit: {limit})")
        
        # First get the matches
        matches = await self.get_player_matches(player_id, limit, game=game)
        
        # Then get stats for each match
        matches_with_stats = []
        for match in matches:
            if match.status.upper() == "FINISHED":
                stats = await self.get_match_stats(match.match_id)
                matches_with_stats.append((match, stats))
            else:
                matches_with_stats.append((match, None))
        
        return matches_with_stats
    
    async def get_multiple_players(self, player_ids: List[str]) -> List[Optional[FaceitPlayer]]:
        """Получить информацию о нескольких игроках параллельно."""
        logger.info(f"Getting multiple players: {len(player_ids)} players")
        
        # Создаём задачи для параллельного выполнения
        tasks = [self.get_player_by_id(player_id) for player_id in player_ids]
        
        # Выполняем с ограничением по concurrency чтобы не перегрузить API
        semaphore = asyncio.Semaphore(5)  # Максимум 5 одновременных запросов
        
        async def limited_task(task):
            async with semaphore:
                return await task
        
        # Выполняем все задачи с ограничениями
        results = await asyncio.gather(*[limited_task(task) for task in tasks], return_exceptions=True)
        
        # Обрабатываем результаты
        players = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Error getting player {player_ids[i]}: {result}")
                players.append(None)
            else:
                players.append(result)
        
        return players
    
    async def get_multiple_player_stats(self, player_ids: List[str], game: str = "cs2") -> List[Optional[Dict[str, Any]]]:
        """Получить статистику нескольких игроков параллельно."""
        logger.info(f"Getting stats for {len(player_ids)} players")
        
        # Создаём задачи для параллельного выполнения
        tasks = [self.get_player_stats(player_id, game) for player_id in player_ids]
        
        # Выполняем с ограничением
        semaphore = asyncio.Semaphore(5)
        
        async def limited_task(task):
            async with semaphore:
                return await task
        
        results = await asyncio.gather(*[limited_task(task) for task in tasks], return_exceptions=True)
        
        # Обрабатываем результаты
        stats_list = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Error getting stats for player {player_ids[i]}: {result}")
                stats_list.append(None)
            else:
                stats_list.append(result)
        
        return stats_list