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

def load_athletic_projections(position: str, format: str) -> pd.DataFrame | None:
    """Loads The Athletic's projections for a given position and format."""
    file_path = config.DATA_DIR / "projections" / f"athletic_{position.lower()}_projections_{format.lower()}.csv"
    if file_path.exists():
        logging.info(f"Loading Athletic projections from: {file_path}")
        return pd.read_csv(file_path, sep='\t')
    logging.warning(f"Athletic projections file not found: {file_path}")
    return None



