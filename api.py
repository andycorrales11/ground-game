from fastapi import FastAPI, HTTPException, Response
from pathlib import Path
import pandas as pd

app      = FastAPI()
SLEEPER_DIR = Path.cwd() / "data" / "sleeper_players"
STATS_DIR = Path.cwd() / "data" / "nfl_stats"

SAFE_COLS = (
    "sleeper_id",
    "full_name",
    "first_name",
    "last_name",
    "position",
    "fantasy_positions", 
    "team",
    "age",
    "height",
    "weight",
    "active",
)

QB_COLS = ['player_id', 'display_name', 'team_abbr', 'completions', 'attempts',
       'passing_yards', 'passing_tds', 'interceptions', 'sacks', 'sack_yards',
       'sack_fumbles', 'sack_fumbles_lost', 'passing_air_yards',
       'passing_yards_after_catch', 'passing_first_downs', 'passing_epa',
       'passing_2pt_conversions', 'pacr', 'fantasy_points', 'fantasy_points_ppr']

RB_COLS = ['player_id', 'display_name', 'team_abbr', 'carries', 'rushing_yards',
       'rushing_tds', 'rushing_fumbles', 'rushing_fumbles_lost',
       'rushing_first_downs', 'rushing_epa', 'rushing_2pt_conversions', 
       'fantasy_points', 'fantasy_points_ppr']

WR_COLS = ['player_id', 'display_name', 'team_abbr', 'receptions', 'targets', 'receiving_yards', 'receiving_tds',
       'receiving_fumbles', 'receiving_fumbles_lost', 'receiving_air_yards',
       'receiving_yards_after_catch', 'receiving_first_downs', 'receiving_epa',
       'receiving_2pt_conversions', 'racr', 'target_share', 'air_yards_share',
       'wopr_x', 'special_teams_tds', 'fantasy_points', 'fantasy_points_ppr',
       'games', 'tgt_sh', 'ay_sh', 'yac_sh', 'wopr_y', 'ry_sh', 'rtd_sh',
       'rfd_sh', 'rtdfd_sh', 'dom', 'w8dom', 'yptmpa', 'ppr_sh']

def _latest_parquet() -> Path:
    files = sorted(SLEEPER_DIR.glob("all_players_*.parquet"))
    if not files:
        raise HTTPException(503, "No player cache found. Run the ingestion script first.")
    return files[-1]

@app.get("/api/players")
def get_players(limit: int | None = None):
    df = pd.read_parquet(_latest_parquet())

    df = df[[c for c in SAFE_COLS if c in df.columns]]
    df = df.dropna(subset=["sleeper_id", "team"])
    if limit:
        df = df.head(limit)

    json_str = df.to_json(orient="records", date_format="iso", default_handler=str)

    return Response(content=json_str, media_type="application/json")

@app.get("/api/players/qbs")
def get_qbs(limit: int | None = None):
    df = pd.read_parquet(STATS_DIR / 'nfl_stats_qbs_2024.parquet')
    df = df[QB_COLS]
    df = df.dropna(subset=["display_name"])
    if limit:
        df = df.head(limit)

    json_str = df.to_json(orient="records", date_format="iso", default_handler=str)
    return Response(content=json_str, media_type="application/json")

@app.get("/api/players/rbs")
def get_rbs(limit: int | None = None):
    df = pd.read_parquet(STATS_DIR / 'nfl_stats_rbs_2024.parquet')
    df = df[RB_COLS]
    df = df.dropna(subset=["display_name"])
    if limit:
        df = df.head(limit)

    json_str = df.to_json(orient="records", date_format="iso", default_handler=str)
    return Response(content=json_str, media_type="application/json")

@app.get("/api/players/wrs")
def get_wrs(limit: int | None = None):
    df = pd.read_parquet(STATS_DIR / 'nfl_stats_wrs_2024.parquet')
    df = df[WR_COLS]
    df = df.dropna(subset=["display_name"])
    if limit:
        df = df.head(limit)

    json_str = df.to_json(orient="records", date_format="iso", default_handler=str)
    return Response(content=json_str, media_type="application/json")