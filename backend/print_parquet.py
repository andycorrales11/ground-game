import pandas as pd
from pathlib import Path
import glob

DATA_DIR = Path.cwd() / "data"
PLAYERS_DIR = DATA_DIR / "sleeper_players"
STATS_DIR = DATA_DIR / "nfl_stats"
ADP_DIR = DATA_DIR / "fantasy_pros_adp"

def print_parquet_file(folder: str, pos = "QB", format = "PPR") -> None:
    """Print the contents of a Parquet file."""
    if folder == "players":
        file_path = PLAYERS_DIR / "all_players_*.parquet"
    elif folder == "stats":
        file_path = STATS_DIR / f"nfl_stats_{pos}*.parquet"
    elif folder == "adp":
        file_path = ADP_DIR / f"FantasyPros_2025_{format}*.csv"
    else:
        raise ValueError("Invalid folder specified. Choose from 'players', 'stats', or 'adp'.")
    
    files = sorted(glob.glob(str(file_path)))
    if not files:
        print(f"No files found in {folder} matching the pattern {file_path}.")
        return
    latest_file = files[-1]  # Get the most recent file
    print(f"Reading from: {latest_file}")
    # Read the Parquet file(s)
    if folder == "adp":
        df = pd.read_csv(latest_file)
    else:
        df = pd.read_parquet(latest_file)

    print(df.head(5))  # Print first 5 rows for brevity
    print(df.columns.tolist())  # Print column names

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Print contents of a Parquet file.")
    parser.add_argument("folder", choices=["players", "stats", "adp"], help="Folder to read from")
    parser.add_argument("--pos", default="QB", help="Position for stats (default: QB)")
    parser.add_argument("--format", default="PPR", help="Format for ADP (default: PPR)")
    
    args = parser.parse_args()
    
    print_parquet_file(args.folder, args.pos, args.format)