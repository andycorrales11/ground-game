"""
This script reads ADP (Average Draft Position) data from multiple formats
and merges it with a master player list.

The final output is a single Parquet file containing player information
and their ADP for each format (e.g., STD, HalfPPR, PPR).
"""
from datetime import datetime, timezone
import glob
import pandas as pd
from backend import config
import logging
import re

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

def normalize_name(name: str) -> str:
    """Normalizes player names for consistent matching."""
    if not isinstance(name, str):
        return name
    name = name.lower()
    name = name.replace("'", "") # Remove apostrophes
    name = re.sub(r'[^a-z0-9\s]', '', name)  # Remove other non-alphanumeric except spaces
    name = re.sub(r'(jr|sr|ii|iii|iv)$', '', name)  # Remove common suffixes at end
    return name.strip()

def _read_adp_parquet(_format: str) -> pd.DataFrame | None:
    """Reads a single ADP parquet file, returning None if not found."""
    try:
        path = config.ADP_DIR / f"FantasyPros_2025_{_format}_ADP.parquet"
        return pd.read_parquet(path)
    except FileNotFoundError:
        logging.warning(f"ADP file not found for format {_format} at {path}")
        return None

def main() -> None:
    """
    Main function to read player data and attach ADP data from multiple formats.
    """
    try:
        # 1. Read the main player data file once
        path = config.PLAYERS_DIR / "all_players_*.parquet"
        files = sorted(glob.glob(str(path)))
        if not files:
            raise FileNotFoundError("No player data files found in the specified directory.")
        
        logging.info(f"Reading player data from {files[-1]}")
        player_df = pd.read_parquet(files[-1])
        
        # 2. Select essential columns and remove duplicate players
        player_df = player_df[['display_name', 'team', 'position', 'age', 'sleeper_id', 'gsis_id']].drop_duplicates(subset=['display_name'])
        player_df['display_name'] = player_df['display_name'].apply(normalize_name)

        # 3. Loop through formats and merge ADP data
        formats = ['STD', 'HalfPPR', 'PPR']
        for _format in formats:
            adp_df = _read_adp_parquet(_format)
            if adp_df is None:
                continue

            logging.info(f"Processing ADP data for format: {_format}")
            
            # Process ADP dataframe
            adp_df['Rank'] = pd.to_numeric(adp_df['Rank'], errors='coerce')
            adp_df['Player'] = adp_df['Player'].apply(normalize_name)
            
            # Rename columns to be format-specific for the merge
            adp_df = adp_df.rename(columns={
                'Player': 'display_name', # Now directly rename to display_name
                'Rank': f'ADP_{_format}',
                'POS': f'pos_adp_{_format}',
                'AVG': f'avg_adp_{_format}'
            })
            
            # Select only the columns needed for the merge
            adp_cols_to_merge = ['display_name', f'ADP_{_format}', f'pos_adp_{_format}', f'avg_adp_{_format}']
            adp_df_to_merge = adp_df[adp_cols_to_merge]

            # Merge ADP data into the main player DataFrame using the normalized name
            player_df = player_df.merge(adp_df_to_merge, on='display_name', how='left')

        # Clean up the final dataframe by dropping players without any ADP data
        player_df.dropna(subset=[f'ADP_{f}' for f in formats], how='all', inplace=True)
        
        # 4. Save the final merged dataframe
        output_path = config.PLAYER_ADP_DIR / f"{datetime.now(timezone.utc).date()}_adp.parquet"
        config.PLAYER_ADP_DIR.mkdir(parents=True, exist_ok=True)
        player_df.to_parquet(output_path, index=False)
        logging.info(f"Successfully saved merged player ADP data to {output_path}")

    except FileNotFoundError as e:
        logging.error(f"File not found: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
