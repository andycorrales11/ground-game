import pandas as pd
from backend.services import data_service

def print_parquet_file(folder: str, pos: str = "QB", format: str = "PPR", player_name: str = None, season: int = 2024) -> None:
    """Print the contents of a Parquet file, optionally filtering by player name."""
    df = None
    print(f"Attempting to load data for folder: '{folder}'")

    if folder == "players":
        df = data_service.load_all_players()
    elif folder == "stats":
        df = data_service.load_stats_data(pos, season)
    elif folder == "adp":
        df = data_service.load_raw_adp_data(format)
    elif folder == "players_adp":
        df = data_service.load_adp_data()
    else:
        raise ValueError("Invalid folder specified. Choose from 'players', 'stats', 'adp', or 'players_adp'.")

    if df is None:
        print(f"No data found for the specified criteria.")
        return

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
    parser.add_argument("--season", type=int, default=2024, help="Season for stats (default: 2024)")

    args = parser.parse_args()

    print_parquet_file(args.folder, args.pos, args.format, player_name=args.name, season=args.season)

