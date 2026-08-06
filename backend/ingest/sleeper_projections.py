"""
Season projections from Sleeper's projections feed.

Replaces the hand-downloaded Athletic CSVs. One request returns every scoring
format at once, keyed by the Sleeper player id that is already this project's
primary key -- so projections join on the id instead of on a normalized name,
which removes the whole class of name-matching failure the CSV path had.

The feed is undocumented. It is the same host family the app already depends on
for live drafts, but it carries no stability guarantee, so everything here fails
loudly rather than silently producing an empty board.
"""
import logging

import pandas as pd
import requests

# Positions the app can actually roster. The raw feed also carries FB, P and the
# occasional IDP row.
FANTASY_POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")

# Sleeper stat key -> database column
POINTS_COLUMNS = {
    "pts_std": "std_proj_pts",
    "pts_half_ppr": "half_ppr_proj_pts",
    "pts_ppr": "ppr_proj_pts",
}

BASE_URL = "https://api.sleeper.com/projections/nfl"
TIMEOUT = 30


def canonical_sleeper_id(value) -> str | None:
    """
    Normalizes a Sleeper id to the plain string form the feed uses.

    nfl_data_py hands back numeric ids, so a bare str() yields "4034.0" while
    Sleeper itself says "4034". Defenses are already abbreviations ("DEN").
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    if text.endswith(".0"):
        text = text[:-2]
    return text


def fetch_projections(season: int) -> pd.DataFrame:
    """
    Fetches season-long projections for every rosterable position.

    Returns a frame of sleeper_id, display_name, team, pos and the three
    *_proj_pts columns. Raises on transport or shape failures.
    """
    params = [("season_type", "regular"), ("order_by", "ppr")]
    params += [("position[]", pos) for pos in FANTASY_POSITIONS]

    url = f"{BASE_URL}/{season}"
    logging.info("Fetching Sleeper projections for %s", season)
    response = requests.get(url, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    rows = response.json()

    if not isinstance(rows, list) or not rows:
        raise ValueError(f"Sleeper returned no projection rows for {season} ({url})")

    records = []
    for row in rows:
        player = row.get("player") or {}
        stats = row.get("stats") or {}

        position = player.get("position")
        if position not in FANTASY_POSITIONS:
            continue

        sleeper_id = canonical_sleeper_id(row.get("player_id"))
        if not sleeper_id:
            continue

        points = {col: stats.get(key) for key, col in POINTS_COLUMNS.items()}
        if all(v is None for v in points.values()):
            continue  # Tracked by Sleeper but not projected; nothing to contribute.

        name = " ".join(
            part for part in (player.get("first_name"), player.get("last_name")) if part
        ).strip()
        if not name:
            continue

        records.append({
            "sleeper_id": sleeper_id,
            "display_name": name,
            "team": row.get("team") or player.get("team"),
            "pos": position,
            **points,
        })

    if not records:
        raise ValueError(
            f"Sleeper returned {len(rows)} rows for {season} but none carried projections. "
            f"The feed shape may have changed."
        )

    df = pd.DataFrame(records)

    # One vendor per season row today, but guard against the feed ever emitting
    # several -- silent duplicates would inflate the board.
    duplicates = df["sleeper_id"].duplicated().sum()
    if duplicates:
        logging.warning("Sleeper returned %s duplicate player ids; keeping the first", duplicates)
        df = df.drop_duplicates(subset=["sleeper_id"], keep="first")

    return df.reset_index(drop=True)
