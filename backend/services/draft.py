import pandas as pd
from typing import List, Dict, Set
from backend import config

class Draft:
    """
    Manages the state of a fantasy football draft, including available players,
    drafted players, and draft settings.
    """
    def __init__(self, players: pd.DataFrame, format: str = config.DEFAULT_DRAFT_FORMAT, teams: int = config.DEFAULT_TEAMS, rounds: int = config.DEFAULT_ROUNDS, roster: List[str] = config.DEFAULT_ROSTER):
        self.players = players
        self.format = format
        self.teams = teams
        self.rounds = rounds
        self.roster = roster
        self.drafted_players: Set[str] = set()

    def get_available_players(self) -> pd.DataFrame:
        """
        Returns a DataFrame of players who have not yet been drafted.
        """
        return self.players[~self.players['display_name'].isin(self.drafted_players)]

    def draft_player(self, player_name: str) -> str | None:
        """
        Marks a player as drafted.

        Args:
            player_name: The display name of the player to draft.

        Returns:
            The position of the drafted player if successful, otherwise None.
        """
        if player_name in self.drafted_players:
            return None  # Player already drafted

        player_row = self.players[self.players['display_name'] == player_name]
        
        if not player_row.empty:
            position = player_row.iloc[0]['position']
            self.drafted_players.add(player_name)
            return position
            
        return None # Player not found

class Team:
    """
    Represents a single team in the fantasy draft, managing its roster.
    """
    def __init__(self, roster: List[str] = config.DEFAULT_ROSTER):
        self.roster: Dict[str, str | None] = {slot: None for slot in roster}
    
    def add_player(self, player: str, pos: str):
        """
        Adds a player to the first available roster slot for their position.
        """
        # Find a position-specific slot first
        for slot in self.roster:
            if slot.startswith(pos) and self.roster[slot] is None:
                self.roster[slot] = player
                return

        # If no position-specific slot, try a FLEX spot for eligible positions
        if pos in ('WR', 'RB', 'TE'):
            for slot in self.roster:
                if slot.startswith('FLEX') and self.roster[slot] is None:
                    self.roster[slot] = player
                    return
        
        # If still no slot, place them on the bench
        for slot in self.roster:
            if slot.startswith('BN') and self.roster[slot] is None:
                self.roster[slot] = player
                return
