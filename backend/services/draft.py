import pandas as pd
from collections import Counter
from typing import List, Dict, Set
from backend import config

# Who can fill the two kinds of open slot. A superflex takes a quarterback --
# that is the entire reason a league runs one -- on top of everyone a plain flex
# takes.
FLEX_ELIGIBLE = ('WR', 'RB', 'TE')
SUPERFLEX_ELIGIBLE = ('QB', 'WR', 'RB', 'TE')

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

    def player_bye(self, player_name: str) -> int | None:
        """
        The bye week for a player, by normalized name.

        Returns None when the player is unknown, when the board predates the bye
        column (the synthetic boards in the tests do), or when the bye itself is
        null -- an unsigned free agent has no team and so no bye.
        """
        if 'bye' not in self.players.columns:
            return None

        rows = self.players.loc[self.players['normalized_name'] == player_name, 'bye']
        if rows.empty:
            return None

        bye = rows.iloc[0]
        return None if pd.isna(bye) else int(bye)

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

        # Bye weeks are tallied the same way and for the same reason: the week is
        # known at add time, and looking it back up would mean matching on a name
        # form the roster does not promise to keep.
        self._bye_weeks: Dict[str, int | None] = {}

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
        clone._bye_weeks = dict(self._bye_weeks)
        return clone

    def add_player(self, player: str, pos: str, bye: int | None = None):
        """
        Adds a player to the first available roster slot for their position.

        The tally is incremented even when no slot is free: a team that has drafted
        three quarterbacks has three regardless of where they sit.

        `bye` is optional because the CPU simulation does not care about bye weeks
        and would rather not carry the column through; a missing bye is simply not
        counted against any week.
        """
        self._position_counts[pos] += 1
        self._bye_weeks[player] = bye

        # Find a position-specific slot first
        for slot in self.roster:
            if slot.startswith(pos) and self.roster[slot] is None:
                self.roster[slot] = player
                return

        # If no position-specific slot, try a FLEX spot for eligible positions,
        # then a superflex. The order matters: a quarterback can only sit in a
        # superflex, so filling one with a running back who had a plain FLEX
        # available would strand the next quarterback on the bench.
        #
        # Note 'SFLEX1'.startswith('FLEX') is False, so the two never collide.
        for eligible, stem in ((FLEX_ELIGIBLE, 'FLEX'), (SUPERFLEX_ELIGIBLE, 'SFLEX')):
            if pos not in eligible:
                continue
            for slot in self.roster:
                if slot.startswith(stem) and self.roster[slot] is None:
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

    def bye_week(self, player: str) -> int | None:
        """The bye week recorded for a rostered player, or None if unknown."""
        return self._bye_weeks.get(player)

    def bye_conflicts(self, threshold: int = 2) -> Dict[int, List[str]]:
        """
        Bye weeks where at least `threshold` rostered players are all out at once.

        Players with an unknown bye are left out rather than bucketed together --
        the 71 unsigned free agents in the pool all have a null bye, and grouping
        them would invent a week where the whole bench disappears.
        """
        weeks: Dict[int, List[str]] = {}
        for player, bye in self._bye_weeks.items():
            if bye is None:
                continue
            weeks.setdefault(int(bye), []).append(player)

        return {
            week: sorted(players)
            for week, players in sorted(weeks.items())
            if len(players) >= threshold
        }

    @property
    def picks_made(self) -> int:
        """
        How many players this team has drafted, whether or not a slot was free.

        This is also the team's round number minus one, which is how the pick
        logic knows how close the draft is to the end without redoing the snake
        arithmetic that already exists in four other places.
        """
        return sum(self._position_counts.values())