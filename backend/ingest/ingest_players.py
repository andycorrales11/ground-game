from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import requests
import pandas as pd

BASE_URL = "https://api.sleeper.app/v1/players/nfl"
OUT_DIR  = Path.cwd() / "data" / "sleeper_players"
OUT_DIR.mkdir(parents=True, exist_ok=True)

'''
This script fetches the full player directory from the Sleeper API and saves it as a Parquet file.
It includes functions to download the data, format it for Parquet storage, and persist it 
in a specified output directory. The player directory contains information about 
NFL players, including their IDs, names, and positions.
'''

# Fetch the full player directory from Sleeper API and save it as a Parquet file.
def _fetch() -> pd.DataFrame:
    """Download the full player directory (~5 MB)."""
    resp = requests.get(BASE_URL, timeout=30)
    resp.raise_for_status()                     
    data = resp.json()                           
    return pd.DataFrame.from_dict(
        data, orient="index"
    ).reset_index(names="sleeper_id")

# Persist the DataFrame to a Parquet file in the output directory.
def _persist(df: pd.DataFrame) -> Path:
    today = datetime.now(timezone.utc).date()
    path = OUT_DIR / f"all_players_{today}.parquet"
    df.to_parquet(path, index=False)
    return path

# Format the DataFrame for Parquet storage, ensuring required fields are present.
def _format_parquet(df: pd.DataFrame) -> pd.DataFrame:
    df.dropna(subset=['gsis_id'], inplace=True)
    df['display_name'] = df['first_name'] + ' ' + df['last_name']
    return df

# Main function to fetch, format, and persist the player data.
def main(force: bool = False) -> None:
    today = datetime.now(timezone.utc).date()
    already = OUT_DIR / f"all_players_{today}.parquet"
    if already.exists() and not force:
        print(f"[info] Already cached: {already}")
        return

    df   = _fetch()
    df   = _format_parquet(df)
    path = _persist(df)
    print(f"[ok] Saved {len(df):,} rows ➜ {path}")


if __name__ == "__main__":
    import argparse, sys

    ap = argparse.ArgumentParser(description="Cache Sleeper all-players list")
    ap.add_argument("--force", action="store_true",
                    help="Ignore existing copy and refetch")
    sys.exit(main(**vars(ap.parse_args())))
    