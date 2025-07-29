import pandas as pd
from backend.services import data_service

def print_db_data(folder: str, pos: str = "QB", format: str = "PPR", player_name: str = None, season: int = 2024) -> None:
    """Print the contents of a database table, optionally filtering by player name."""
    df = None
    print(f"Attempting to load data for: '{folder}'")

    if folder == "players":
        df = data_service.load_player_data()
    else:
        raise ValueError("Invalid folder specified. Choose from 'players'.")

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
    parser = argparse.ArgumentParser(description="Print contents of a database table.")
    parser.add_argument("folder", choices=["players"], help="Table to read from")
    parser.add_argument("--pos", default="QB", help="Position for stats (default: QB)")
    parser.add_argument("--format", default="PPR", help="Format for ADP (default: PPR)")
    parser.add_argument("--name", help="Filter by player name (case-insensitive)")
    parser.add_argument("--season", type=int, default=2024, help="Season for stats (default: 2024)")

    args = parser.parse_args()

    print_db_data(args.folder, args.pos, args.format, player_name=args.name, season=args.season)

