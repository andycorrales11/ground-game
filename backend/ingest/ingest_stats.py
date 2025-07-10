"""
This script processes NFL player statistics for a given season, separates them by position,
and saves the data into position-specific Parquet files.
"""
import nfl_data_py as nfl
import pandas as pd
from backend import config
from .stat_columns import player_columns, qb_columns, rb_columns, wr_columns
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

def process_position(df: pd.DataFrame, position: str, columns: list[str], sort_by: str, season: int):
    """
    Filters, processes, and saves data for a specific position.
    """
    logging.info(f"Processing stats for {position}s...")
    
    # Filter for position and merge with stats
    pos_df = df[df['position'] == position].copy()
    pos_df = pos_df.merge(seasonal_data[columns], on='player_id', how='inner')
    
    # Clean and sort data
    pos_df.dropna(subset=[sort_by, 'display_name'], inplace=True)
    pos_df.sort_values(by=sort_by, ascending=False, inplace=True)
    
    # Save to file
    output_path = config.STATS_DIR / f"nfl_stats_{position.lower()}s_{season}.parquet"
    pos_df.to_parquet(output_path, index=False)
    logging.info(f"Saved {position} stats to {output_path}")

def main(season: int = 2024) -> None:
    """
    Main function to ingest and process seasonal NFL stats.
    """
    try:
        config.STATS_DIR.mkdir(parents=True, exist_ok=True)

        # 1. Import base data once
        logging.info(f"Importing seasonal data for {season}...")
        global seasonal_data
        seasonal_data = nfl.import_seasonal_data([season])
        
        logging.info("Importing player data...")
        players_df = nfl.import_players()[player_columns].rename(columns={'gsis_id': 'player_id'})
        players_df['display_name'] = players_df['display_name'].apply(normalize_name) # Apply normalization here

        # 2. Define position-specific processing details
        positions_to_process = {
            'QB': {'cols': qb_columns, 'sort': 'passing_yards'},
            'RB': {'cols': rb_columns, 'sort': 'rushing_yards'},
            'WR': {'cols': wr_columns, 'sort': 'receiving_yards'},
            'TE': {'cols': wr_columns, 'sort': 'receiving_yards'} # TEs use WR columns
        }

        # 3. Loop and process each position
        for position, details in positions_to_process.items():
            process_position(
                df=players_df,
                position=position,
                columns=details['cols'],
                sort_by=details['sort'],
                season=season
            )

        logging.info("All positions processed successfully.")

    except Exception as e:
        logging.error(f"An unexpected error occurred in ingest_stats: {e}")

if __name__ == "__main__":
    main(2024)