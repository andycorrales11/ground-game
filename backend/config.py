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
