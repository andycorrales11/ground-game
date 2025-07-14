from pathlib import Path
from typing import List

# --- DIRECTORIES ---
CWD = Path.cwd()
DATA_DIR = CWD / "data"
PLAYERS_DIR = DATA_DIR / "sleeper_players"
STATS_DIR = DATA_DIR / "nfl_stats"
ADP_DIR = DATA_DIR / "fantasy_pros_adp"
PLAYER_ADP_DIR = DATA_DIR / "players_adp"

# --- DRAFT SETTINGS ---
DEFAULT_ROSTER: List[str] = [
    "QB1", "RB1", "RB2", "WR1", "WR2", "TE1", "FLEX1", "FLEX2",
    "K", "DEF", "BN1", "BN2", "BN3", "BN4", "BN5", "BN6",
    "BN7", "BN8"
]

# Positional mapping for VBD calculations
DEFAULT_ROSTER_POS: List[str] = [
    "QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "FLEX",
    "K", "DEF", "BN", "BN", "BN", "BN", "BN", "BN", "BN", "BN"
]

DEFAULT_TEAMS: int = 12
DEFAULT_ROUNDS: int = 20
DEFAULT_DRAFT_FORMAT: str = 'STD'

# VORP positional adjustments
POSITION_ADJUSTMENT: dict = {
    "QB": 0.8,
    "RB": 1.0,
    "WR": 1.0,
    "TE": 1.0
}
