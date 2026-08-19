import os
import re
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv
import nfl_data_py as nfl

from backend import config
from backend.ingest import sleeper_projections
from backend.ingest.sleeper_projections import canonical_sleeper_id
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

# FantasyPros has shipped at least two different export layouts. Try each naming
# convention in turn so a season's files work whichever export was downloaded.
ADP_FILENAME_PATTERNS = [
    "FantasyPros_{season}_Overall_ADP_Rankings_{label}.csv",  # 2026 "Overall ADP Rankings"
    "FantasyPros_{season}_{label}_ADP.csv",                   # 2025 "ADP" export
]

# "Jahmyr Gibbs   DET (6)" -> name / team / bye. The team and bye are optional:
# unsigned free agents are listed as a bare name. Defenses come through as
# "Houston Texans DST   (8)", which lands team="DST" -- the same placeholder the
# older export used, so DEFENSE_TEAM_ABBR still resolves them.
PLAYER_BYE_RE = re.compile(
    r"^(?P<name>.+?)(?:\s+(?P<team>[A-Z]{2,3})\s*\((?P<bye>\d+)\))?$"
)

DB_COLUMNS = [
    "sleeper_id", "display_name", "normalized_name", "team", "pos", "bye",
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

# The sources disagree on a few team abbreviations. FantasyPros writes "JAC" for
# Jacksonville's players while Sleeper writes "JAX", which split the roster into
# two teams and gave the board 33 of them -- caught by the count check in
# _fill_byes_from_team. Canonical form is Sleeper's, since that is what
# DEFENSE_TEAM_ABBR already produces and what the live draft feed sends.
TEAM_ABBR_ALIASES = {
    "JAC": "JAX",
    "WSH": "WAS",
    "LA": "LAR",
    "ARZ": "ARI",
    "BLT": "BAL",
    "CLV": "CLE",
    "HST": "HOU",
}

# nfl_data_py disagrees with FantasyPros on a handful of names. Suffix-only
# differences ("Travis Etienne Jr.") do NOT belong here -- the normalized fallback
# in _resolve_sleeper_id handles those. This is for genuinely different spellings.
NAME_MAP = {
    "Deebo Samuel Sr.": "Deebo Samuel",
    "Brian Robinson Jr.": "Brian Robinson",
    "Anthony Richardson Sr.": "Anthony Richardson",
    "Aaron Jones Sr.": "Aaron Jones",
    "Kenny Gainwell": "Kenneth Gainwell",
    "Chig Okonkwo": "Chigoziem Okonkwo",
    "Hollywood Brown": "Marquise Brown",
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


def _build_name_index(names, positions, raw_ids) -> list[dict]:
    """
    Builds the lookups used to resolve a FantasyPros name to a Sleeper id, most
    specific first: (exact name, pos), exact name, (normalized name, pos),
    normalized name.

    Both halves matter.

    Position is what separates players who genuinely share a name. nflverse lists
    two Lamar Jacksons (the Ravens QB and a Panthers CB) and two Justin Jeffersons
    (the Vikings WR and a 2026 Browns LB). Picking by name alone is a coin flip,
    and it lands on the wrong one often enough to strip the ADP off a first-round
    player.

    Normalization is what bridges suffixes, which FantasyPros writes and nflverse
    mostly does not -- "James Cook III" against "James Cook", "Patrick Mahomes II"
    against "Patrick Mahomes".

    A key that still covers two different ids is dropped rather than guessed at,
    so an ambiguous name falls through to the next lookup or goes unresolved and
    gets reported.
    """
    buckets: list[dict] = [{}, {}, {}, {}]

    for name, pos, raw in zip(names, positions, raw_ids):
        sid = canonical_sleeper_id(raw)
        if not sid or not isinstance(name, str):
            continue
        norm = normalize_name(name)
        keys = [None, name, None, norm]
        if isinstance(pos, str) and pos:
            keys[0] = (name, pos.upper())
            keys[2] = (norm, pos.upper())
        for bucket, key in zip(buckets, keys):
            if key is not None:
                bucket.setdefault(key, set()).add(sid)

    return [
        {k: next(iter(v)) for k, v in bucket.items() if len(v) == 1}
        for bucket in buckets
    ]


def _resolve_sleeper_id(name, pos, index: list[dict]) -> str | None:
    """Resolves one FantasyPros player name to a Sleeper id, most specific first."""
    mapped = NAME_MAP.get(name, name)
    if not isinstance(mapped, str):
        return None

    norm = normalize_name(mapped)
    upper_pos = pos.upper() if isinstance(pos, str) and pos else None
    for bucket, key in zip(index, [(mapped, upper_pos), mapped, (norm, upper_pos), norm]):
        if isinstance(key, tuple) and key[1] is None:
            continue
        sid = bucket.get(key)
        if sid:
            return sid
    return None


def _resolve_adp_file(season: int, label: str, adp_dir: Path) -> Path:
    """Finds a season's ADP file under any of the known FantasyPros naming conventions."""
    tried = []
    for pattern in ADP_FILENAME_PATTERNS:
        path = adp_dir / pattern.format(season=season, label=label)
        if path.exists():
            return path
        tried.append(path.name)
    raise FileNotFoundError(
        f"No {label} ADP file for {season} in {adp_dir}.\n"
        f"Looked for: {', '.join(tried)}\n"
        f"Download the {season} FantasyPros ADP CSVs (Standard, Half PPR, PPR) into that directory."
    )


def _normalize_adp_frame(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """
    Reduces either FantasyPros export layout to Player / POS / Team / Bye / AVG.

    The newer "Overall ADP Rankings" export drops the Team and Bye columns and
    folds them into the player cell ("Jahmyr Gibbs   DET (6)"), and carries a
    variable set of per-site columns that differ between the three files.
    """
    if "AVG" not in df.columns or "POS" not in df.columns:
        raise ValueError(f"{source} is missing expected columns: needs POS and AVG")

    if "Player" in df.columns and "Team" in df.columns:
        out = df[["Player", "POS", "Team", "AVG"]].copy()
        # The older export carries Bye as its own column. Treat it as optional so a
        # layout without one still loads -- _fill_byes_from_team can recover it from
        # the team anyway.
        out["Bye"] = pd.to_numeric(df["Bye"], errors="coerce") if "Bye" in df.columns else pd.NA
        return out

    if "Player (Bye)" not in df.columns:
        raise ValueError(
            f"{source} has neither a 'Player'+'Team' pair nor a 'Player (Bye)' column. "
            f"Columns present: {list(df.columns)}"
        )

    parts = df["Player (Bye)"].astype(str).str.strip().str.extract(PLAYER_BYE_RE)
    out = pd.DataFrame({
        "Player": parts["name"].str.strip(),
        "POS": df["POS"],
        "Team": parts["team"],  # NaN for unsigned free agents
        "Bye": pd.to_numeric(parts["bye"], errors="coerce"),
        "AVG": df["AVG"],
    })

    unsigned = int(out["Team"].isna().sum())
    if unsigned:
        print(f"    {source}: {unsigned} row(s) with no team (unsigned free agents)")
    return out


def load_adp_data(season: int, adp_dir: Path) -> pd.DataFrame:
    """
    Loads the three FantasyPros ADP CSVs and merges them into a single frame.

    POS, Team and Bye are coalesced across all three files. Taking them from the
    STD file alone leaves every player absent from that file with no position,
    which is most of the deep WR/TE pool.
    """
    frames = {}
    for label, adp_col in ADP_FORMATS.items():
        path = _resolve_adp_file(season, label, adp_dir)
        df = _normalize_adp_frame(pd.read_csv(path), path.name)
        print(f"  {label:<8} {len(df):>4} rows from {path.name}")
        frames[adp_col] = df.rename(columns={"AVG": adp_col})

    # First non-null POS/Team/Bye across all three files wins -- groupby.first()
    # skips NaN, so a player listed in only one file still keeps their identity.
    identity = pd.concat(
        [df[["Player", "POS", "Team", "Bye"]] for df in frames.values()], ignore_index=True
    ).groupby("Player", as_index=False).first()

    adp_data = identity
    for adp_col, df in frames.items():
        adp_data = pd.merge(adp_data, df[["Player", adp_col]], on="Player", how="outer")

    return adp_data


def _merge_sleeper_projections(board: pd.DataFrame, season: int) -> pd.DataFrame:
    """
    Joins Sleeper projections onto the ADP board by Sleeper id.

    Players Sleeper projects but FantasyPros does not list are kept: they have no
    ADP, so they sort to the bottom of the board, but they are the deep-league and
    waiver pool. Their name, team and position come from Sleeper.
    """
    projections = sleeper_projections.fetch_projections(season)
    print(f"  Sleeper returned {len(projections)} projected players.")

    board = _fill_ids_from_projections(board, projections)

    merged = pd.merge(board, projections, on="sleeper_id", how="outer", suffixes=("", "_sleeper"))

    # The ADP file is authoritative for anyone it lists; Sleeper fills the rest.
    for column in ("display_name", "team", "pos"):
        merged[column] = merged[column].fillna(merged[f"{column}_sleeper"])
    merged.drop(columns=[f"{c}_sleeper" for c in ("display_name", "team", "pos")], inplace=True)

    matched = int(board["sleeper_id"].isin(projections["sleeper_id"]).sum())
    drafted = int(board["sleeper_id"].notna().sum())
    print(f"  Matched projections for {matched}/{drafted} players with an ADP.")
    if drafted and matched / drafted < 0.8:
        print("    Warning: under 80% matched -- check that the season and ids line up.")

    return merged


def _build_adp_board(season: int) -> pd.DataFrame:
    """ADP, position, team and resolved Sleeper id for every drafted player."""
    adp_data = load_adp_data(season, config.ADP_DIR)
    board = adp_data.rename(columns={"Player": "display_name", "Team": "team", "Bye": "bye"})

    # FantasyPros encodes positional rank in POS ("WR12"); strip it, then normalize
    # its "DST" to the "DEF" used by config.DEFAULT_ROSTER.
    board["pos"] = board["POS"].str.replace(r"\d+$", "", regex=True)
    board["pos"] = board["pos"].replace({"DST": "DEF", "D/ST": "DEF"})
    board.drop(columns=["POS"], inplace=True)

    # Defenses carry the literal "DST" in the team column, so resolve them by name.
    is_def = board["pos"] == "DEF"
    board.loc[is_def, "team"] = board.loc[is_def, "display_name"].map(DEFENSE_TEAM_ABBR)
    unmapped_def = board[is_def & board["team"].isna()]
    if not unmapped_def.empty:
        print("\n  Warning: unrecognized defense name(s), add them to DEFENSE_TEAM_ABBR:")
        for name in unmapped_def["display_name"]:
            print(f"    - {name}")

    # --- Sleeper IDs ---
    player_ids = get_sleeper_ids()
    index = _build_name_index(
        player_ids["name"], player_ids["position"], player_ids["sleeper_id"]
    )
    board["sleeper_id"] = [
        _resolve_sleeper_id(name, pos, index)
        for name, pos in zip(board["display_name"], board["pos"])
    ]
    # nfl_data_py only covers players, so team defenses never resolve. Sleeper keys
    # defenses by the team abbreviation itself ("DEN"), so use that as the id.
    board.loc[is_def, "sleeper_id"] = board.loc[is_def, "team"]

    resolved = board["sleeper_id"].notna().sum()
    print(f"  Resolved Sleeper ids for {resolved}/{len(board)} ADP rows.")

    # Keep unresolved rows here; _fill_ids_from_projections gets a second attempt
    # before prepare_data drops whatever is still unidentifiable.
    identified = board[board["sleeper_id"].notna()].drop_duplicates(
        subset=["sleeper_id"], keep="first"
    )
    return pd.concat([identified, board[board["sleeper_id"].isna()]], ignore_index=True)


def _fill_ids_from_projections(board: pd.DataFrame, projections: pd.DataFrame) -> pd.DataFrame:
    """
    Second pass at the ADP rows nflverse could not identify.

    Sleeper's projection feed is keyed by the same ids and carries Sleeper's own
    spelling, so it resolves players nflverse is missing entirely -- rookie kickers
    especially, who nflverse tends not to have until they play a snap. Matching is
    on normalized name *and* position, so two players sharing a name cannot swap.
    """
    missing = board["sleeper_id"].isna()
    if not missing.any():
        return board

    index = _build_name_index(
        projections["display_name"], projections["pos"], projections["sleeper_id"]
    )
    taken = set(board.loc[~missing, "sleeper_id"])

    filled = []
    for name, pos in zip(board.loc[missing, "display_name"], board.loc[missing, "pos"]):
        sid = _resolve_sleeper_id(name, pos, index)
        filled.append(None if sid in taken else sid)

    board.loc[missing, "sleeper_id"] = filled
    recovered = sum(1 for sid in filled if sid)
    if recovered:
        print(f"  Recovered {recovered} more id(s) from Sleeper's projection feed.")

    # Dedupe only the identified rows. drop_duplicates treats every NaN key as
    # equal to every other, so running it across the whole frame would collapse
    # all the still-unidentified players into a single row and hide them from the
    # report that is supposed to name them.
    identified = board[board["sleeper_id"].notna()].drop_duplicates(
        subset=["sleeper_id"], keep="first"
    )
    return pd.concat([identified, board[board["sleeper_id"].isna()]], ignore_index=True)


def _canonicalize_teams(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reduces each team to one abbreviation so the two sources agree.

    Anything keyed on team -- bye weeks, and any future stacking or scarcity work --
    silently treats "JAC" and "JAX" as different franchises otherwise.
    """
    before = set(df["team"].dropna())
    df["team"] = df["team"].replace(TEAM_ABBR_ALIASES)
    merged_away = sorted(before - set(df["team"].dropna()))
    if merged_away:
        print(f"  Teams: folded {', '.join(merged_away)} into their canonical form.")
    return df


def _fill_byes_from_team(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fills missing bye weeks from the player's team.

    A bye week is a property of the NFL team, not the player, so one row per team
    is enough to date the other 50. This is what covers everyone FantasyPros does
    not list -- the projection-only deep pool, who arrive from Sleeper with a team
    but no ADP row to carry a bye -- and defenses, whose team abbreviation is their
    id.

    The per-team value is the mode rather than the first, so a single malformed row
    cannot redate a whole roster.
    """
    if "bye" not in df.columns:
        df["bye"] = pd.NA
        return df

    df["bye"] = pd.to_numeric(df["bye"], errors="coerce")

    known = df.dropna(subset=["team", "bye"])
    if known.empty:
        print("  Warning: no bye weeks parsed from the ADP files at all.")
        return df

    team_bye = known.groupby("team")["bye"].agg(lambda s: s.mode().iloc[0])

    missing = df["bye"].isna() & df["team"].notna()
    df.loc[missing, "bye"] = df.loc[missing, "team"].map(team_bye)

    recovered = int(missing.sum() - (df["bye"].isna() & df["team"].notna()).sum())
    print(f"  Byes: {len(team_bye)} teams dated; recovered {recovered} player(s) from their team.")
    if len(team_bye) != 32:
        print(f"    Warning: expected 32 teams with a bye, got {len(team_bye)}.")

    return df


def prepare_data(season: int | None = None) -> pd.DataFrame:
    """
    Builds the players table from FantasyPros ADP plus Sleeper projections.

    Sleeper covers every scoring format in one request and joins on the Sleeper
    id rather than on a name, so there is no name matching on this path at all.

    The stored projections are a *fallback* now rather than the board's numbers.
    Quarterbacks, running backs, receivers and tight ends are reprojected at draft
    time by backend/services/projection_engine.py, against the league's own
    scoring; what survives from here is kickers, defenses, and the deep pool the
    engine does not model.

    (An Athletic-CSV path used to live alongside this one, joining on display
    name. The projection engine supersedes it and it has been removed.)
    """
    season = season or config.SEASON
    print(f"Preparing data for the {season} season.")

    board = _build_adp_board(season)
    merged = _merge_sleeper_projections(board, season)

    merged["normalized_name"] = merged["display_name"].apply(normalize_name)
    merged = _canonicalize_teams(merged)
    merged = _fill_byes_from_team(merged)

    final_data = merged.reindex(columns=DB_COLUMNS).copy()

    # bye is an INT column. Carried as a float it would reach COPY as "6.0", which
    # Postgres rejects; Int64 keeps it whole while still allowing a null.
    final_data["bye"] = final_data["bye"].astype("Int64")

    # sleeper_id is the primary key, so rows without one cannot be stored. These are
    # dropped ADP rows -- the player is losing their ADP, so report them by ADP and
    # not alphabetically. Anything here inside the draftable range needs a NAME_MAP
    # entry; everything past ~round 20 is noise.
    unresolved = final_data[final_data["sleeper_id"].isna()]
    if not unresolved.empty:
        print(f"\n  Dropping {len(unresolved)} row(s) with no Sleeper ID, best ADP first:")
        ranked = unresolved.sort_values("ppr_adp", na_position="last")
        for _, row in ranked.head(15).iterrows():
            print(f"    - adp={str(row['ppr_adp']):<8} {row['display_name']} ({row['pos']})")
        draftable = ranked[ranked["ppr_adp"] <= 200]
        if not draftable.empty:
            print(f"    Warning: {len(draftable)} of these are inside ADP 200 and "
                  f"should be added to NAME_MAP.")
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

    gap_columns = [c for c in DB_COLUMNS if c.endswith(("_adp", "_proj_pts"))] + ["pos", "team", "bye"]
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
