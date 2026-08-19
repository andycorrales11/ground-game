"""
Loads projection inputs from the workbook into the database.

    .\\.venv\\Scripts\\python.exe -m backend.ingest.ingest_projections

Unlike `ingest_to_db`, this writes *inputs* rather than finished numbers -- team
volume, share weights, efficiency rates -- so the app can score them against
whatever the league pays. Nothing here computes a fantasy point.

Each run inserts a new `projection_sets` row and makes it active, leaving the
previous set in place. Re-importing a corrected workbook is therefore
non-destructive, and last week's numbers stay available to diff against.

Resolution to `sleeper_id` is by name, which is unavoidable: the workbook has no
identifier the rest of the world shares. Whatever fails to resolve is still
stored -- see `_resolve` for why that is not optional.
"""
import argparse
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from backend import config
from backend.ingest.ingest_to_db import TEAM_ABBR_ALIASES
from backend.ingest.workbook import load_workbook_projections
from backend.services import data_service
from backend.services.projection_engine import PlayerRates, ProjectionInputs
from backend.utils import normalize_name

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

DEFAULT_WORKBOOK = '2026-FFB-Projections-0817.xlsx'

# Spellings the workbook uses that the board does not. Keep this to genuinely
# different names: suffixes and punctuation are handled by `normalize_name`, and
# a team change is handled by the fallback tiers in `_resolve`.
#
# Note this is *not* the same map as `ingest_to_db.NAME_MAP`, and in one case it
# points the other way -- FantasyPros writes "Kenny Gainwell" where nflverse
# writes "Kenneth", and the board is built from the FantasyPros spelling, so the
# workbook's "Kenneth" has to come back the other direction.
NAME_MAP = {
    'Kenneth Gainwell': 'Kenny Gainwell',
    'Dermarcus Robinson': 'Demarcus Robinson',
}

RATE_COLUMNS = (
    'w_pass', 'w_rush', 'w_tgt',
    'comp_pct', 'yds_per_comp', 'pass_td_pct', 'int_pct',
    'rush_ypc', 'rush_td_rate',
    'catch_rate', 'yds_per_rec', 'rec_td_rate',
)


def _canonical_team(team: str) -> str:
    """
    The board's spelling of a team abbreviation.

    The workbook writes WSH where the board writes WAS. Left alone that is two
    franchises, and every Commander fails to resolve.
    """
    return TEAM_ABBR_ALIASES.get(team, team)


def _build_index(board) -> Dict[tuple, set]:
    """
    Lookup keys for every player on the board, most specific first.

    A key that covers two different players is kept and rejected at lookup time
    rather than silently resolving to whichever row came first -- there are two
    Lamar Jacksons and two Justin Jeffersons in the league, and guessing between
    them strips the projection off a first-round player.
    """
    index: Dict[tuple, set] = {}
    for row in board.itertuples():
        name = row.normalized_name or normalize_name(row.display_name)
        if not name:
            continue
        for key in ((name, row.pos, row.team), (name, row.pos), (name,)):
            index.setdefault(key, set()).add(row.sleeper_id)
    return index


def _resolve(player: PlayerRates, index: Dict[tuple, set]) -> str | None:
    """
    A workbook player's `sleeper_id`, or None.

    None is a normal outcome, not a failure to handle later: the workbook
    projects a fourth receiver on every roster and the board carries only players
    with an ADP or a Sleeper projection. Those players are still stored and still
    projected, because the share weights are relative -- dropping them would
    renormalize their teammates' shares upward and quietly change every
    projection on the team.
    """
    name = normalize_name(NAME_MAP.get(player.name, player.name))
    team = _canonical_team(player.team)

    for key in ((name, player.pos, team), (name, player.pos), (name,)):
        matches = index.get(key, set())
        if len(matches) == 1:
            return next(iter(matches))
    return None


def resolve_players(
    inputs: ProjectionInputs, board
) -> Tuple[Dict[Tuple[str, int], str], List[PlayerRates]]:
    """Maps (team, key) to sleeper_id, and returns whatever did not resolve."""
    index = _build_index(board)

    resolved: Dict[Tuple[str, int], str] = {}
    unmatched: List[PlayerRates] = []
    for player in inputs.players:
        sleeper_id = _resolve(player, index)
        if sleeper_id is None:
            unmatched.append(player)
        else:
            resolved[(player.team, player.key)] = sleeper_id

    return resolved, unmatched


def _report(inputs: ProjectionInputs, unmatched: Iterable[PlayerRates]) -> None:
    """
    Says out loud what did not resolve.

    An import that quietly drops a starting running back looks exactly like a
    clean one, so the unmatched list is printed in full rather than counted.
    """
    unmatched = list(unmatched)
    total = len(inputs.players)
    matched = total - len(unmatched)
    log.info(
        "Resolved %d of %d players to a sleeper_id (%.1f%%).",
        matched, total, 100.0 * matched / total if total else 0.0,
    )

    if not unmatched:
        return

    log.warning(
        "%d player(s) did not resolve. They are still stored and still projected "
        "-- their share weights hold their teammates' shares down -- but they "
        "will not appear on the draft board:", len(unmatched),
    )
    for player in sorted(unmatched, key=lambda p: (p.pos, p.team, p.name)):
        log.warning("    %-3s %-3s %s", player.pos, player.team, player.name)


def write_set(
    inputs: ProjectionInputs,
    resolved: Dict[Tuple[str, int], str],
    source: str,
    label: str | None,
    season: int,
) -> int:
    """
    Inserts a new projection set and makes it the active one.

    The previous set is deactivated rather than deleted. The whole write is one
    transaction: a half-imported set that was already marked active would be a
    board with a random subset of the league missing.
    """
    connection = data_service.get_db_connection()
    if connection is None:
        raise RuntimeError("Could not connect to the database.")

    with connection:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE projection_sets SET is_active = FALSE WHERE is_active")
            cursor.execute(
                """
                INSERT INTO projection_sets (source, label, season, is_active)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id
                """,
                (source, label, season),
            )
            set_id = cursor.fetchone()[0]

            cursor.executemany(
                """
                INSERT INTO projection_teams (set_id, team, plays, pass_pct, rush_ypc)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (set_id, _canonical_team(v.team), v.plays, v.pass_pct, v.rush_ypc)
                    for v in inputs.volumes.values()
                ],
            )

            columns = ', '.join(RATE_COLUMNS)
            placeholders = ', '.join(['%s'] * len(RATE_COLUMNS))
            cursor.executemany(
                f"""
                INSERT INTO projection_players (
                    set_id, team, player_key, sleeper_id,
                    display_name, normalized_name, pos, {columns}
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, {placeholders})
                """,
                [
                    (
                        set_id,
                        _canonical_team(p.team),
                        p.key,
                        resolved.get((p.team, p.key)),
                        p.name,
                        normalize_name(p.name),
                        p.pos,
                        *(getattr(p, column) for column in RATE_COLUMNS),
                    )
                    for p in inputs.players
                ],
            )

    connection.close()
    return set_id


def ingest(workbook: Path, label: str | None = None, season: int | None = None) -> int:
    inputs = load_workbook_projections(workbook)
    log.info(
        "Parsed %d players across %d teams from %s.",
        len(inputs.players), len(inputs.volumes), workbook.name,
    )

    board = data_service.load_player_data()
    if board is None or board.empty:
        raise RuntimeError(
            "The players table is empty. Run backend.ingest.ingest_to_db first -- "
            "projections resolve against the board, not the other way round."
        )

    resolved, unmatched = resolve_players(inputs, board)
    _report(inputs, unmatched)

    set_id = write_set(
        inputs,
        resolved,
        source=workbook.name,
        label=label,
        season=season if season is not None else config.SEASON,
    )
    log.info("Wrote projection set %d and made it active.", set_id)
    return set_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--workbook',
        type=Path,
        default=config.DATA_DIR / DEFAULT_WORKBOOK,
        help='Path to the projection workbook.',
    )
    parser.add_argument('--label', help='A note stored with the set, e.g. "week 1".')
    parser.add_argument('--season', type=int, default=None)
    args = parser.parse_args()

    if not args.workbook.exists():
        raise SystemExit(
            f"Workbook not found: {args.workbook}\n"
            f"data/ is gitignored; download the workbook there first."
        )

    ingest(args.workbook, label=args.label, season=args.season)


if __name__ == '__main__':
    main()
