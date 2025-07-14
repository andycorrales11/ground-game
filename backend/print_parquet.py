import glob
import pandas as pd
from backend import config

def print_parquet_file(folder: str, pos: str = "QB", format: str = "PPR", player_name: str = None) -> None:
    """Print the contents of a Parquet file, optionally filtering by player name."""
    file_path = None
    if folder == "players":
        file_path = config.PLAYERS_DIR / "all_players_*.parquet"
    elif folder == "stats":
        file_path = config.STATS_DIR / f"nfl_stats_{pos}*.parquet"
    elif folder == "adp":
        file_path = config.ADP_DIR / f"FantasyPros_2025_{format}*.parquet"
    elif folder == "players_adp":
        file_path = config.PLAYER_ADP_DIR / "*_adp.parquet"
    else:
        raise ValueError("Invalid folder specified. Choose from 'players', 'stats', 'adp', or 'players_adp'.")
    
    files = sorted(glob.glob(str(file_path)))
    if not files:
        print(f"No files found in {folder} matching the pattern {file_path}.")
        return
    latest_file = files[-1]  # Get the most recent file
    print(f"Reading from: {latest_file}")
    
    df = pd.read_parquet(latest_file)

    if player_name:
        # Filter by player name if provided
        filtered_df = df[df['display_name'].str.contains(player_name, case=False, na=False)]
        if not filtered_df.empty:
            print(filtered_df)
        else:
            print(f"No player found with the name '{player_name}'.")
    else:
        print(df.head(10))  # Print first 10 rows for brevity
    
    print("\nColumns:", df.columns.tolist())  # Print column names

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Print contents of a Parquet file.")
    parser.add_argument("folder", choices=["players", "stats", "adp", "players_adp"], help="Folder to read from")
    parser.add_argument("--pos", default="QB", help="Position for stats (default: QB)")
    parser.add_argument("--format", default="PPR", help="Format for ADP (default: PPR)")
    parser.add_argument("--name", help="Filter by player name (case-insensitive)")

    args = parser.parse_args()

    print_parquet_file(args.folder, args.pos, args.format, player_name=args.name)
