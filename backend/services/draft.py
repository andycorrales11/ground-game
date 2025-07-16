import pandas as pd
from typing import List, Dict, Set
from backend import config

class Draft:
    """
    Manages the state of a fantasy football draft, including available players,
    drafted players, and draft settings.
    """
    def __init__(self, players: pd.DataFrame, format: str = config.DEFAULT_DRAFT_FORMAT, teams: int = config.DEFAULT_TEAMS, rounds: int = config.DEFAULT_ROUNDS, roster: List[str] = config.DEFAULT_ROSTER, order: str = 'snake'):
        self.players = players
        self.format = format
        self.teams = teams
        self.rounds = rounds
        self.roster = roster
        self.order = order
        self.drafted_players: Set[str] = set()

    def get_available_players(self) -> pd.DataFrame:
        """
        Returns a DataFrame of players who have not yet been drafted.
        """
        return self.players[~self.players['normalized_name'].isin(self.drafted_players)]

    def draft_player(self, player_name: str) -> str | None:
        """
        Marks a player as drafted.

        Args:
            player_name: The display name of the player to draft.

        Returns:
            The position of the drafted player if successful, otherwise None.
        """
        # player_name is display_name. Find the corresponding row.
        player_rows = self.players[self.players['display_name'] == player_name]
        
        if player_rows.empty:
            return None # Player not found

        # Find the first non-drafted player with this name
        for index, row in player_rows.iterrows():
            normalized_name = row['normalized_name']
            if normalized_name not in self.drafted_players:
                self.drafted_players.add(normalized_name)
                return row['position']

        return None # Player already drafted

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

    def get_positional_needs(self) -> List[str]:
        """
        Identifies all unfilled positions on the roster, including bench.
        """
        needs = []
        # Use a set to avoid duplicate position checks
        positions_to_check = set(cfg.rstrip('0123456789') for cfg in self.roster.keys())
        
        for pos in positions_to_check:
            if pos == 'BN': continue # Skip bench
            
            slots_for_pos = [s for s in self.roster.keys() if s.startswith(pos)]
            filled_slots = [s for s in slots_for_pos if self.roster[s] is not None]
            
            if len(filled_slots) < len(slots_for_pos):
                needs.append(pos)
        return needs

    def get_starting_positional_needs(self) -> List[str]:
        """
        Identifies unfilled positions in the starting lineup only.
        """
        needs = []
        # Exclude bench slots from consideration
        starting_slots = [slot for slot in self.roster.keys() if not slot.startswith('BN')]
        positions_to_check = set(cfg.rstrip('0123456789') for cfg in starting_slots)

        for pos in positions_to_check:
            slots_for_pos = [s for s in starting_slots if s.startswith(pos)]
            filled_slots = [s for s in slots_for_pos if self.roster[s] is not None]
            
            if len(filled_slots) < len(slots_for_pos):
                needs.append(pos)
        return needs

    def count_players_at_position(self, pos: str, player_df: pd.DataFrame) -> int:
        """
        Counts the number of players of a specific position on the team.
        """
        count = 0
        # Get the display names of players on the roster
        rostered_players = [name for name in self.roster.values() if name is not None]
        if not rostered_players:
            return 0
        
        # Filter the main player DataFrame to get the positions of rostered players
        roster_details = player_df[player_df['display_name'].isin(rostered_players)]
        
        # Count how many have the specified position
        if not roster_details.empty:
            count = roster_details[roster_details['position'] == pos].shape[0]
            
        return count