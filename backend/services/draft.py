import pandas as pd
from collections import Counter
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
        # player_name is normalized_name. Find the corresponding row.
        player_rows = self.players[self.players['normalized_name'] == player_name]
        
        if player_rows.empty:
            return None # Player not found

        # Find the first non-drafted player with this name
        for index, row in player_rows.iterrows():
            normalized_name = row['normalized_name']
            if normalized_name not in self.drafted_players:
                self.drafted_players.add(normalized_name)
                return row['pos']

        return None # Player already drafted

class Team:
    """
    Represents a single team in the fantasy draft, managing its roster.
    """
    def __init__(self, roster: List[str] = config.DEFAULT_ROSTER):
        self.roster: Dict[str, str | None] = {slot: None for slot in roster}

        # Positions are tallied as players arrive rather than looked up afterwards
        # against the big board. Callers disagree about which name form goes into
        # the roster -- normalized in draft_manager_service, display name in the
        # VONA simulation -- so the old name-based lookup silently counted zero and
        # the CPU's third-QB penalty never fired. `pos` is known at add time.
        self._position_counts: Counter = Counter()

    def copy(self) -> "Team":
        """
        A detached duplicate with the roster and tallies intact.

        The VONA forward simulation used to build its teams with
        `Team(roster=t.roster.copy())`. The constructor takes slot *names*, so
        iterating a roster dict handed it the keys and produced an empty team --
        every CPU team entered the simulation as though the draft had not started,
        which made positional need and the QB penalty inert exactly when the draft
        is far enough along for them to matter.
        """
        clone = Team(list(self.roster.keys()))
        clone.roster = dict(self.roster)
        clone._position_counts = self._position_counts.copy()
        return clone

    def add_player(self, player: str, pos: str):
        """
        Adds a player to the first available roster slot for their position.

        The tally is incremented even when no slot is free: a team that has drafted
        three quarterbacks has three regardless of where they sit.
        """
        self._position_counts[pos] += 1

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

    def count_players_at_position(self, pos: str) -> int:
        """
        Counts the number of players of a specific position on the team.
        """
        return self._position_counts[pos]

    @property
    def picks_made(self) -> int:
        """
        How many players this team has drafted, whether or not a slot was free.

        This is also the team's round number minus one, which is how the pick
        logic knows how close the draft is to the end without redoing the snake
        arithmetic that already exists in four other places.
        """
        return sum(self._position_counts.values())