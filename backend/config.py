import os
from pathlib import Path
from typing import List

# --- SEASON ---
# The season the ingest reads CSVs for. Override without editing code by setting
# GG_SEASON in the environment (e.g. GG_SEASON=2027).
SEASON: int = int(os.getenv("GG_SEASON", "2026"))

# --- DIRECTORIES ---
CWD = Path.cwd()
DATA_DIR = CWD / "data"
PLAYERS_DIR = DATA_DIR / "sleeper_players"
STATS_DIR = DATA_DIR / "nfl_stats"
ADP_DIR = DATA_DIR / "fantasy_pros_adp"
PROJECTIONS_DIR = DATA_DIR / "projections"
PLAYER_ADP_DIR = DATA_DIR / "players_adp"

# --- DRAFT SETTINGS ---
# The starting lineup is a league rule and does not vary with draft length.
DEFAULT_STARTERS: List[str] = [
    "QB1", "RB1", "RB2", "WR1", "WR2", "TE1", "FLEX1", "FLEX2", "K", "DEF"
]

DEFAULT_TEAMS: int = 12
DEFAULT_ROUNDS: int = 20


def roster_slots(rounds: int) -> List[str]:
    """
    Roster slots for a draft of `rounds` rounds: the fixed starting lineup, then
    exactly enough bench to hold every pick that is not a starter.

    The bench has to be sized from the draft, not fixed. A hardcoded eight-slot
    bench meant a 20-round draft had two picks with nowhere to sit -- `add_player`
    tallies them but drops them off the roster panel -- while a 10-round draft
    showed eight bench slots that could never be filled.

    A draft shorter than the starting lineup gets no bench at all and leaves
    starting slots empty, which is what actually happens in such a league.
    """
    bench = max(0, rounds - len(DEFAULT_STARTERS))
    return DEFAULT_STARTERS + [f"BN{i}" for i in range(1, bench + 1)]


DEFAULT_ROSTER: List[str] = roster_slots(DEFAULT_ROUNDS)

# Positional mapping for VBD calculations. Only the starters matter here --
# `calculate_vorp` counts starting slots per position to find replacement level,
# and bench depth does not move it.
DEFAULT_ROSTER_POS: List[str] = [
    "QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX", "K", "DEF"
]
DEFAULT_DRAFT_FORMAT: str = 'STD'

# Positions VORP is computed for. K and DEF were excluded while the Athletic CSVs
# were the projection source, because those files never covered them -- which left
# every kicker and defense pinned at VORP 0. Sleeper projects them, so they now get
# a real value like everyone else.
VORP_POSITIONS: List[str] = ["QB", "RB", "WR", "TE", "K", "DEF"]

# VORP positional adjustments. Anything absent is 1.0.
POSITION_ADJUSTMENT: dict = {
    "QB": 0.8,
    "RB": 1.0,
    "WR": 1.0,
    "TE": 1.0
}
