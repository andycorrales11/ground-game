"""
This script reads ADP (Average Draft Position) data from CSV files
and attaches it to a DataFrame containing player information.

It supports multiple formats (STD, HalfPPR, PPR) and merges
the ADP data with the player DataFrame based on the player's display name
"""
from pathlib import Path
from datetime import datetime, timezone
import glob
import pandas as pd



DATA_DIR = Path.cwd() / "data"


def _read_adp_csv(_format: str) -> pd.DataFrame:
    """Read a CSV file into a DataFrame."""
    return pd.read_csv(f"{DATA_DIR}/fantasy_pros_adp/FantasyPros_2025_{_format}_ADP.csv", dtype=str)

def _read_adp_parquet(_format: str) -> pd.DataFrame:
    return pd.read_parquet(f"{DATA_DIR}/fantasy_pros_adp/FantasyPros_2025_{_format}_ADP.parquet")
def _attach_adp(df: pd.DataFrame, _format: str) -> pd.DataFrame:
    """Attach ADP data to the DataFrame."""
    try:
        adp_df = _read_adp_parquet(_format)
        print(adp_df.head(10))
        # Convert 'adp' column to numeric, coercing errors to NaN
        adp_df['Rank'] = pd.to_numeric(adp_df['Rank'], errors='coerce')
        adp_df = adp_df.rename(columns={
            'Player': 'display_name', 'Rank': 'ADP', 
            'POS': 'pos_adp', 'AVG': 'avg_adp'})
        # Merge ADP data with the main DataFrame
        df = df[['display_name', 'team', 'position', 'age', 'sleeper_id', 'gsis_id']]
        df = adp_df.merge(df, on='display_name', how='left', suffixes=('', f'_{_format}'))
        df = df.dropna(subset=['display_name', 'ADP'])
        df = df.drop_duplicates(subset=['display_name'])
        return df
    except FileNotFoundError as e:
        print(f"[error] ADP file not found for format {_format}: {e}")
        return df


def main() -> None:
    """Main function to read player data and attach ADP."""
    try:
        path = DATA_DIR / "sleeper_players/all_players_*.parquet"
        files = sorted(glob.glob(str(path)))
        if not files:
            raise FileNotFoundError("No player data files found in the specified directory.")
        df = pd.read_parquet(files[-1])
        formats = ['STD', 'HalfPPR', 'PPR']
        for _format in formats:
            df = _attach_adp(df, _format)
        df.to_parquet(DATA_DIR / "players_adp" / f"{datetime.now(timezone.utc).date()}_adp.parquet")
    except ValueError as e:
        print(f"[error] {e}")
    except FileNotFoundError as e:
        print(f"[error] {e}")
    except OSError as e:
        print(f"[error] {e}")


if __name__ == "__main__":
    main()
