"""FACEIT API data models."""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class FaceitGame(BaseModel):
    """FACEIT game information."""
    region: str
    game_player_id: str
    skill_level: int
    faceit_elo: int
    game_player_name: str
    skill_level_label: str
    game_profile_id: str


class FaceitPlayer(BaseModel):
    """FACEIT player information."""
    player_id: str
    nickname: str
    avatar: str
    country: str
    games: Dict[str, FaceitGame] = Field(default_factory=dict)


class FaceitTeamPlayer(BaseModel):
    """Team player in match."""
    player_id: str
    nickname: str
    avatar: str


class FaceitTeam(BaseModel):
    """FACEIT team information."""
    team_id: Optional[str] = Field(None, alias="faction_id")
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    type: Optional[str] = None
    players: List[FaceitTeamPlayer] = Field(default_factory=list)


class MatchResults(BaseModel):
    """Match results."""
    winner: str
    score: Dict[str, int]


class PlayerMatchHistory(BaseModel):
    """Player match from history."""
    match_id: str
    game_id: str
    region: str
    match_type: str
    game_mode: str
    max_players: int
    teams_size: int
    teams: Dict[str, FaceitTeam]
    playing_players: List[str]
    competition_id: str
    competition_name: str
    competition_type: str
    organizer_id: str
    status: str
    started_at: int
    finished_at: int
    results: MatchResults
    faceit_url: str


class FaceitMatch(BaseModel):
    """Detailed match information."""
    match_id: str
    version: Optional[int] = None
    game: Optional[str] = None
    region: Optional[str] = None
    competition_id: Optional[str] = None
    competition_name: Optional[str] = None
    competition_type: Optional[str] = None
    organizer_id: Optional[str] = None
    teams: Optional[Dict[str, FaceitTeam]] = Field(default_factory=dict)
    playing_players: Optional[List[str]] = Field(default_factory=list)
    competition: Optional[str] = None
    configured_at: Optional[int] = None
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
    demo_url: Optional[List[str]] = None
    chat_room_id: Optional[str] = None
    best_of: Optional[int] = None
    results: Optional[MatchResults] = None
    status: Optional[str] = None
    faceit_url: Optional[str] = None


class PlayerStats(BaseModel):
    """Player statistics in a match."""
    player_id: str
    nickname: str
    player_stats: Dict[str, str] = Field(default_factory=dict)


class TeamStats(BaseModel):
    """Team statistics."""
    team_id: str
    premade: bool
    team_stats: Dict[str, str] = Field(default_factory=dict)
    players: List[PlayerStats] = Field(default_factory=list)


class RoundStats(BaseModel):
    """Round statistics."""
    Map: str
    Rounds: str
    Score: str
    Winner: str


class MatchRound(BaseModel):
    """Match round information."""
    best_of: str
    competition_id: Optional[str] = None
    game_id: str
    game_mode: str
    match_id: str
    match_round: str
    played: str
    round_stats: RoundStats
    teams: List[TeamStats] = Field(default_factory=list)


class MatchStatsResponse(BaseModel):
    """Complete match statistics response."""
    rounds: List[MatchRound] = Field(default_factory=list)