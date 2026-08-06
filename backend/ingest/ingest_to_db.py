import os
import re
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
import nfl_data_py as nfl

from backend import config
from backend.utils import normalize_name

# Load environment variables from .env file
load_dotenv()

# --- DATABASE CONNECTION ---
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# FantasyPros filename label -> database column
ADP_FORMATS = {
    "STD": "std_adp",
    "HalfPPR": "half_ppr_adp",
    "PPR": "ppr_adp",
}

# e.g. athletic_qb_projections_halfppr.csv
PROJ_FILE_RE = re.compile(
    r"^athletic_(?P<pos>[a-z]+)_projections_(?P<fmt>std|ppr|halfppr)\.csv$",
    re.IGNORECASE,
)

DB_COLUMNS = [
    "sleeper_id", "display_name", "normalized_name", "team", "pos",
    "std_adp", "half_ppr_adp", "ppr_adp",
    "std_proj_pts", "half_ppr_proj_pts", "ppr_proj_pts",
]

# FantasyPros lists defenses by full team name with Team set to the literal "DST",
# so the abbreviation has to come from the name. Sleeper keys defenses by these
# same abbreviations.
DEFENSE_TEAM_ABBR = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LAR", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}

# nfl_data_py disagrees with FantasyPros on a handful of names.
NAME_MAP = {
    "Deebo Samuel Sr.": "Deebo Samuel",
    "Brian Robinson Jr.": "Brian Robinson",
    "Anthony Richardson Sr.": "Anthony Richardson",
    "Aaron Jones Sr.": "Aaron Jones",
}


def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg.connect(
            host=DB_HOST,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except psycopg.OperationalError as e:
        print(f"Error connecting to the database: {e}")
        return None


def get_sleeper_ids():
    """Gets Sleeper IDs for a list of player names using nfl_data_py."""
    player_ids_df = nfl.import_ids()
    return player_ids_df


def load_adp_data(season: int, adp_dir: Path) -> pd.DataFrame:
    """
    Loads the three FantasyPros ADP CSVs and merges them into a single frame.

    POS and Team are coalesced across all three files. Taking them from the STD
    file alone leaves every player absent from that file with no position, which
    is most of the deep WR/TE pool.
    """
    frames = {}
    for label, adp_col in ADP_FORMATS.items():
        path = adp_dir / f"FantasyPros_{season}_{label}_ADP.csv"
        if not path.exists():
            raise FileNotFoundError(
                f"Missing ADP file: {path}\n"
                f"Download the {season} FantasyPros ADP CSVs (Standard, Half PPR, PPR) into {adp_dir}."
            )
        df = pd.read_csv(path)
        missing = {"Player", "POS", "Team", "AVG"} - set(df.columns)
        if missing:
            raise ValueError(f"{path.name} is missing expected columns: {sorted(missing)}")
        frames[adp_col] = df[["Player", "POS", "Team", "AVG"]].rename(columns={"AVG": adp_col})

    # First non-null POS/Team across all three files wins.
    identity = pd.concat(
        [df[["Player", "POS", "Team"]] for df in frames.values()], ignore_index=True
    ).groupby("Player", as_index=False).first()

    adp_data = identity
    for adp_col, df in frames.items():
        adp_data = pd.merge(adp_data, df[["Player", adp_col]], on="Player", how="outer")

    return adp_data


def load_projection_data(proj_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Loads the Athletic projection CSVs (tab-separated despite the .csv extension).

    Returns (projections, hints). The hints carry the position encoded in each
    filename plus the team column, which together are the only position/team source
    for players who appear in the projections but in none of the ADP files.
    """
    by_format: dict[str, list[pd.DataFrame]] = {"std": [], "ppr": [], "half_ppr": []}
    hints: list[pd.DataFrame] = []

    for path in sorted(proj_dir.glob("*.csv")):
        match = PROJ_FILE_RE.match(path.name)
        if not match:
            print(f"  Warning: unrecognized projection filename, skipping: {path.name}")
            continue

        fmt = match.group("fmt").lower().replace("halfppr", "half_ppr")
        file_pos = match.group("pos").upper()

        try:
            raw = pd.read_csv(path, sep="\t")
            df = raw[["Player", "FPS"]].rename(columns={"Player": "display_name"})
        except Exception as e:
            print(f"  Error processing {path.name}: {e}")
            continue

        hints.append(pd.DataFrame({
            "display_name": df["display_name"],
            "pos_hint": file_pos,
            "team_hint": raw["TM"] if "TM" in raw.columns else None,
        }))
        by_format[fmt].append(df.rename(columns={"FPS": f"{fmt}_proj_pts"}))

    projections = None
    for fmt, dfs in by_format.items():
        if not dfs:
            print(f"  Warning: no {fmt} projection files found in {proj_dir}.")
            continue
        frame = pd.concat(dfs, ignore_index=True).groupby("display_name", as_index=False).first()
        projections = frame if projections is None else pd.merge(
            projections, frame, on="display_name", how="outer"
        )

    if projections is None:
        raise FileNotFoundError(
            f"No usable projection files found in {proj_dir}. Expected files named like "
            f"'athletic_rb_projections_ppr.csv'."
        )

    hint_df = (
        pd.concat(hints, ignore_index=True).groupby("display_name", as_index=False).first()
        if hints
        else pd.DataFrame(columns=["display_name", "pos_hint", "team_hint"])
    )
    return projections, hint_df


def prepare_data(season: int | None = None) -> pd.DataFrame:
    """Reads and prepares player data from CSV files."""
    season = season or config.SEASON
    print(f"Preparing data for the {season} season.")

    adp_data = load_adp_data(season, config.ADP_DIR)
    projections, hints = load_projection_data(config.PROJECTIONS_DIR)

    # --- Merge ADP and projections ---
    merged = pd.merge(
        adp_data, projections, left_on="Player", right_on="display_name", how="outer"
    )
    merged["display_name"] = merged["display_name"].fillna(merged["Player"])
    merged.drop(columns=["Player"], inplace=True)
    merged = pd.merge(merged, hints, on="display_name", how="left")

    # --- Position ---
    # FantasyPros encodes positional rank in POS ("WR12"); strip it. Fall back to
    # the position implied by the projection filename, then normalize FantasyPros'
    # "DST" to the "DEF" used by config.DEFAULT_ROSTER.
    pos_from_adp = merged["POS"].str.replace(r"\d+$", "", regex=True)
    merged["pos"] = pos_from_adp.fillna(merged["pos_hint"])
    merged["pos"] = merged["pos"].replace({"DST": "DEF", "D/ST": "DEF"})

    # --- Team ---
    # Fall back to the projections' TM column, then resolve defenses, whose Team
    # column is the useless literal "DST".
    merged.rename(columns={"Team": "team"}, inplace=True)
    merged["team"] = merged["team"].fillna(merged["team_hint"])
    is_def = merged["pos"] == "DEF"
    merged.loc[is_def, "team"] = merged.loc[is_def, "display_name"].map(DEFENSE_TEAM_ABBR)
    unmapped_def = merged[is_def & merged["team"].isna()]
    if not unmapped_def.empty:
        print("\n  Warning: unrecognized defense name(s), add them to DEFENSE_TEAM_ABBR:")
        for name in unmapped_def["display_name"]:
            print(f"    - {name}")

    merged["normalized_name"] = merged["display_name"].apply(normalize_name)

    # --- Sleeper IDs ---
    player_ids = get_sleeper_ids()
    id_map = dict(zip(player_ids["name"], player_ids["sleeper_id"]))
    merged["sleeper_id"] = merged["display_name"].apply(
        lambda name: id_map.get(NAME_MAP.get(name, name))
    )

    # nfl_data_py only covers players, so team defenses never resolve. Sleeper keys
    # defenses by the team abbreviation itself ("DEN"), so use that as the id.
    merged.loc[is_def, "sleeper_id"] = merged.loc[is_def, "team"]

    merged.drop_duplicates(subset=["sleeper_id"], keep="first", inplace=True)

    final_data = merged.reindex(columns=DB_COLUMNS).copy()

    # sleeper_id is the primary key, so rows without one cannot be stored.
    unresolved = final_data[final_data["sleeper_id"].isna()]
    if not unresolved.empty:
        print(f"\n  Dropping {len(unresolved)} row(s) with no Sleeper ID (first 10):")
        for name in unresolved["display_name"].head(10):
            print(f"    - {name}")
    final_data.dropna(subset=["sleeper_id"], inplace=True)

    _report_gaps(final_data)

    # Convert every pandas NaN/NA to None so it lands as a real SQL NULL. Written
    # as-is, a NaN becomes the literal string 'nan' in a varchar column and an IEEE
    # NaN in a double precision column -- neither of which "IS NULL" ever matches.
    final_data = final_data.astype(object).where(pd.notna(final_data), None)

    return final_data


def _report_gaps(df: pd.DataFrame) -> None:
    """Prints what is missing so bad source data is visible instead of silent."""
    print(f"\n  {len(df)} players prepared.")

    counts = df["pos"].value_counts(dropna=False)
    print("  By position:")
    for pos, n in counts.items():
        label = "(none)" if pd.isna(pos) else pos
        print(f"    {label:<8} {n}")

    gap_columns = [c for c in DB_COLUMNS if c.endswith(("_adp", "_proj_pts"))] + ["pos", "team"]
    gaps = {col: int(df[col].isna().sum()) for col in gap_columns}
    gaps = {col: n for col, n in gaps.items() if n}
    if gaps:
        print("  Missing values (stored as NULL):")
        for col, n in gaps.items():
            print(f"    {col:<20} {n}")
    else:
        print("  No missing values.")


def ingest_data(data):
    """Ingests the prepared data into the PostgreSQL database."""
    conn = get_db_connection()
    if not conn:
        return

    with conn.cursor() as cur:
        # Clear existing data
        cur.execute("TRUNCATE TABLE players RESTART IDENTITY;")
        print("Players table truncated.")

        data_to_insert = [tuple(row) for row in data.itertuples(index=False)]

        try:
            columns = ", ".join(DB_COLUMNS)
            with cur.copy(f"COPY players ({columns}) FROM STDIN") as copy:
                for record in data_to_insert:
                    copy.write_row(record)
            conn.commit()
            print(f"{len(data_to_insert)} records inserted successfully.")
        except Exception as e:
            print(f"Error during bulk insert: {e}")
            conn.rollback()

    conn.close()


if __name__ == "__main__":
    print("Starting data preparation...")
    prepared_data = prepare_data()
    print("Data preparation complete.")
    print("Starting data ingestion...")
    ingest_data(prepared_data)
    print("Data ingestion complete.")
