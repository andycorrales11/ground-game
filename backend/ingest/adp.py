import pandas as pd
from pathlib import Path

DATA_DIR = Path.cwd() / "data"

# Read ADP files for different formats
def _read_adp_csv(format: str) -> pd.DataFrame:
    """Read a CSV file into a DataFrame."""
    return pd.read_csv(f"{DATA_DIR}/fantasy_pros_adp/FantasyPros_2025_{format}_ADP.csv", dtype=str)

def _attach_adp(df: pd.DataFrame, format: str) -> pd.DataFrame:
    """Attach ADP data to the DataFrame."""
    adp_df = _read_adp_csv(format)
    
    # Convert 'adp' column to numeric, coercing errors to NaN
    adp_df['adp'] = pd.to_numeric(adp_df['adp'], errors='coerce')
    adp_df.rename(columns={'Player': 'display_name', 'Rank': 'ADP', 'POS': 'pos_adp', 'AVG': 'avg_adp'})
    # Merge ADP data with the main DataFrame
    df = df.merge(adp_df[['display_name', 'ADP', 'pos_adp', 'avg_adp']], on='display_name', how='left', suffixes=('', f'_{format}'))
    print(df.head(5))
    return df

def main() -> None:
    pd.read_parquet(DATA_DIR + "/sleeper_players/all_players*.parquet")