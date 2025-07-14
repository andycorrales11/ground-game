"""
Service for loading data from the file system.
"""
import glob
import logging
import os
import pandas as pd
from backend import config

def _get_latest_file(path_pattern: str) -> str | None:
    """Gets the most recent file matching a glob pattern."""
    files = glob.glob(path_pattern)
    if not files:
        logging.warning(f"No files found matching pattern: {path_pattern}")
        return None
    return max(files, key=os.path.getctime)

def load_adp_data() -> pd.DataFrame | None:
    """Loads the latest player ADP data."""
    path_pattern = str(config.PLAYER_ADP_DIR / "*_adp.parquet")
    latest_file = _get_latest_file(path_pattern)
    if latest_file:
        logging.info(f"Loading ADP data from: {latest_file}")
        return pd.read_parquet(latest_file)
    return None

def load_raw_adp_data(format: str = "PPR") -> pd.DataFrame | None:
    """Loads the latest raw ADP data for a specific format."""
    path_pattern = str(config.ADP_DIR / f"FantasyPros_2025_{format}*.parquet")
    latest_file = _get_latest_file(path_pattern)
    if latest_file:
        logging.info(f"Loading raw ADP data from: {latest_file}")
        return pd.read_parquet(latest_file)
    return None

def load_stats_data(position: str, season: int) -> pd.DataFrame | None:
    """Loads player stats for a given position and season."""
    file_path = config.STATS_DIR / f"nfl_stats_{position.lower()}s_{season}.parquet"
    if file_path.exists():
        logging.info(f"Loading stats data from: {file_path}")
        return pd.read_parquet(file_path)
    logging.warning(f"Stats file not found: {file_path}")
    return None

def load_all_players() -> pd.DataFrame | None:
    """Loads the latest 'all_players' data."""
    path_pattern = str(config.PLAYERS_DIR / "all_players_*.parquet")
    latest_file = _get_latest_file(path_pattern)
    if latest_file:
        logging.info(f"Loading all players data from: {latest_file}")
        return pd.read_parquet(latest_file)
    return None