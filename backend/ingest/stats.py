import nfl_data_py as nfl
import pandas as pd
from pathlib import Path
from stat_columns import player_columns, qb_columns, rb_columns, wr_columns
'''
This script processes NFL player statistics for a given season and saves the data in Parquet format.
It retrieves seasonal data, filters players by position, and merges their stats with player information.
The processed data is saved in a structured directory for easy access and analysis.
'''

OUT_DIR = Path.cwd() / "data" / "nfl_stats"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PLAYERS_PATH = Path.cwd() / "data" / "sleeper_players"

# Function to get the latest Sleeper players Parquet file
def _latest_sleeper_parquet() -> Path:
    files = sorted(PLAYERS_PATH.glob("all_players_*.parquet"))
    return files[-1] if files else None

# Function to process NFL statistics for a given season
def _process(season: int = 2024) -> None:
    seasonal_data = nfl.import_seasonal_data([season])
    players = nfl.import_players()[player_columns].rename(columns={'gsis_id':'player_id'})

    qbs = players[players['position'] == 'QB']
    qbs = qbs.merge(seasonal_data[qb_columns], on='player_id', how='outer').dropna(subset=['passing_yards']).sort_values(by='passing_yards', ascending=False)
    qbs.to_parquet(OUT_DIR / f"nfl_stats_qbs_{season}.parquet", index=False)
    
    rbs = players[players['position'] == 'RB']
    rbs = rbs.merge(seasonal_data[rb_columns], on='player_id', how='outer').dropna(subset=['rushing_yards']).sort_values(by='rushing_yards', ascending=False)
    rbs.to_parquet(OUT_DIR / f"nfl_stats_rbs_{season}.parquet", index=False)

    wrs = players[players['position'] == 'WR']
    wrs = wrs.merge(seasonal_data[wr_columns], on='player_id', how='outer').dropna(subset=['receiving_yards']).sort_values(by='receiving_yards', ascending=False)
    wrs.to_parquet(OUT_DIR / f"nfl_stats_wrs_{season}.parquet", index=False)

    tes = players[players['position'] == 'TE']
    tes = tes.merge(seasonal_data[wr_columns], on='player_id', how='outer').dropna(subset=['receiving_yards']).sort_values(by='receiving_yards', ascending=False)
    tes.to_parquet(OUT_DIR / f"nfl_stats_tes_{season}.parquet", index=False)
        
#   sleeper_players = pd.read_parquet(_latest_sleeper_parquet())

if __name__ == "__main__":
    _process(2024)
