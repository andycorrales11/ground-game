import nfl_data_py as nfl
import pandas as pd
from pathlib import Path


OUT_DIR = Path.cwd() / "data" / "nfl_stats"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PLAYERS_PATH = Path.cwd() / "data" / "sleeper_players"

seasonal_columns = ['player_id', 'season', 'season_type', 'completions', 'attempts',
       'passing_yards', 'passing_tds', 'interceptions', 'sacks', 'sack_yards',
       'sack_fumbles', 'sack_fumbles_lost', 'passing_air_yards',
       'passing_yards_after_catch', 'passing_first_downs', 'passing_epa',
       'passing_2pt_conversions', 'pacr', 'carries', 'rushing_yards',
       'rushing_tds', 'rushing_fumbles', 'rushing_fumbles_lost',
       'rushing_first_downs', 'rushing_epa', 'rushing_2pt_conversions',
       'receptions', 'targets', 'receiving_yards', 'receiving_tds',
       'receiving_fumbles', 'receiving_fumbles_lost', 'receiving_air_yards',
       'receiving_yards_after_catch', 'receiving_first_downs', 'receiving_epa',
       'receiving_2pt_conversions', 'racr', 'target_share', 'air_yards_share',
       'wopr_x', 'special_teams_tds', 'fantasy_points', 'fantasy_points_ppr',
       'games', 'tgt_sh', 'ay_sh', 'yac_sh', 'wopr_y', 'ry_sh', 'rtd_sh',
       'rfd_sh', 'rtdfd_sh', 'dom', 'w8dom', 'yptmpa', 'ppr_sh']

player_columns = ['first_name', 'last_name', 'position', 'gsis_id',
       'display_name', 'current_team_id','jersey_number',
       'position_group', 'short_name', 'smart_id', 'status',
       'status_description_abbr', 'status_short_description', 'team_abbr',
       'uniform_number', 'height', 'weight', 'college_name',
       'years_of_experience', 'birth_date', 'team_seq', 'suffix']

qb_columns = ['player_id', 'season', 'season_type', 'completions', 'attempts',
       'passing_yards', 'passing_tds', 'interceptions', 'sacks', 'sack_yards',
       'sack_fumbles', 'sack_fumbles_lost', 'passing_air_yards',
       'passing_yards_after_catch', 'passing_first_downs', 'passing_epa',
       'passing_2pt_conversions', 'pacr', 'fantasy_points', 'fantasy_points_ppr']

rb_columns = ['player_id', 'season', 'season_type', 'carries', 'rushing_yards',
       'rushing_tds', 'rushing_fumbles', 'rushing_fumbles_lost',
       'rushing_first_downs', 'rushing_epa', 'rushing_2pt_conversions', 
       'fantasy_points', 'fantasy_points_ppr']

wr_columns = ['player_id', 'season', 'season_type', 'receptions', 'targets', 'receiving_yards', 'receiving_tds',
       'receiving_fumbles', 'receiving_fumbles_lost', 'receiving_air_yards',
       'receiving_yards_after_catch', 'receiving_first_downs', 'receiving_epa',
       'receiving_2pt_conversions', 'racr', 'target_share', 'air_yards_share',
       'wopr_x', 'special_teams_tds', 'fantasy_points', 'fantasy_points_ppr',
       'games', 'tgt_sh', 'ay_sh', 'yac_sh', 'wopr_y', 'ry_sh', 'rtd_sh',
       'rfd_sh', 'rtdfd_sh', 'dom', 'w8dom', 'yptmpa', 'ppr_sh']
def _latest_sleeper_parquet() -> Path:
    files = sorted(PLAYERS_PATH.glob("all_players_*.parquet"))
    return files[-1] if files else None

def _process(season: int = 2024) -> None:
    seasonal_data = nfl.import_seasonal_data([season])
    players = nfl.import_players()[player_columns].rename(columns={'gsis_id':'player_id'})

    qbs = players[players['position'] == 'QB']
    qbs = qbs.merge(seasonal_data[qb_columns], on='player_id', how='outer').dropna(subset=['passing_yards'])
    qbs.to_parquet(OUT_DIR / f"nfl_stats_qbs_{season}.parquet", index=False)
    
    rbs = players[players['position'] == 'RB']
    rbs = rbs.merge(seasonal_data[rb_columns], on='player_id', how='outer').dropna(subset=['rushing_yards'])
    rbs.to_parquet(OUT_DIR / f"nfl_stats_rbs_{season}.parquet", index=False)

    wrs = players[players['position'] == 'WR']
    wrs = wrs.merge(seasonal_data[wr_columns], on='player_id', how='outer').dropna(subset=['receiving_yards'])
    wrs.to_parquet(OUT_DIR / f"nfl_stats_wrs_{season}.parquet", index=False)

#     tes = players[players['position'] == 'TE']
        
#    sleeper_players = pd.read_parquet(_latest_sleeper_parquet())

def main(season: int = 2024) -> None:
     _process(season)

if __name__ == "__main__":
    main()
