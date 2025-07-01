"""
This script reads ADP (Average Draft Position) data from CSV files
and attaches it to a DataFrame containing player information.

It supports multiple formats (STD, HalfPPR, PPR) and merges
the ADP data with the player DataFrame based on the player's display name
"""
from pathlib import Path
import glob
import pandas as pd



DATA_DIR = Path.cwd() / "data"


def _read_adp_csv(_format: str) -> pd.DataFrame:
    """Read a CSV file into a DataFrame."""
    return pd.read_csv(f"{DATA_DIR}/fantasy_pros_adp/FantasyPros_2025_{_format}_ADP.csv", dtype=str)


def _attach_adp(df: pd.DataFrame, _format: str) -> pd.DataFrame:
    """Attach ADP data to the DataFrame."""
    try:
        adp_df = _read_adp_csv(_format)
        # Convert 'adp' column to numeric, coercing errors to NaN
        adp_df['Rank'] = pd.to_numeric(adp_df['Rank'], errors='coerce')
        adp_df = adp_df.rename(columns={
            'Player': 'display_name', 'Rank': 'ADP', 
            'POS': 'pos_adp', 'AVG': 'avg_adp'})
        # Merge ADP data with the main DataFrame
        df = df.merge(adp_df[['display_name', 'ADP', 'pos_adp', 'avg_adp']],
                       on='display_name', how='left', suffixes=('', f'_{_format}'))
        print(df.head(5))
        return df
    except FileNotFoundError as e:
        print(f"[error] ADP file not found for format {_format}: {e}")
        return df


def main() -> None:
    """Main function to read player data and attach ADP."""
    try:
        path = DATA_DIR / "sleeper_players/all_players_*.parquet"
        files = sorted(glob.glob(str(path)))
        print(files)
        if not files:
            raise FileNotFoundError("No player data files found in the specified directory.")
        df = pd.read_parquet(files[-1])
        formats = ['STD', 'HalfPPR', 'PPR']
        for _format in formats:
            df = _attach_adp(df, _format)
        print(df.columns.tolist())  # Print column names
        print(df.head(5))  # Print first 5 rows for brevity
    except FileNotFoundError as e:
        print(f"[error] {e}")


if __name__ == "__main__":
    main()
