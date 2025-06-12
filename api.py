from fastapi import FastAPI, HTTPException, Response
from pathlib import Path
import pandas as pd

app      = FastAPI()
DATA_DIR = Path.cwd() / "data" / "sleeper_players"

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

def _latest_parquet() -> Path:
    files = sorted(DATA_DIR.glob("all_players_*.parquet"))
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
