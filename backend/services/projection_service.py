"""
Reads projection inputs out of the database and scores them for a league.

This is the seam between storage and the engine. `projection_engine` knows
nothing about Postgres and `data_service` knows nothing about football; this
module joins them and hands back one thing: what each player is projected to
score under a given set of scoring rules.

Inputs are cached per set. They are immutable once written -- a re-import creates
a new set rather than editing one -- so the cache never has to be invalidated,
only extended. Scoring is deliberately *not* cached: a full recompute is a few
hundred players of arithmetic, and caching it would mean keying on the scoring
settings, which is more bookkeeping than the microseconds are worth.
"""
import logging
from typing import Dict, List

import pandas as pd

from backend.league import ScoringSettings
from backend.services import data_service
from backend.services.projection_engine import (
    PlayerRates,
    ProjectionInputs,
    TeamVolume,
    project_all,
)

log = logging.getLogger(__name__)

# Loaded sets, keyed by set id. Sets are append-only, so entries never go stale.
_INPUT_CACHE: Dict[int, ProjectionInputs] = {}

# (team, player_key) -> sleeper_id, per set. Kept beside the inputs rather than
# inside them because the engine has no business knowing a player has an id
# anywhere else.
_ID_CACHE: Dict[int, Dict[tuple, str]] = {}


def active_set_id() -> int | None:
    """The projection set the board should be built from, or None if there is none."""
    connection = data_service.get_db_connection()
    if connection is None:
        return None

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM projection_sets WHERE is_active LIMIT 1")
            row = cursor.fetchone()
    except Exception as error:  # noqa: BLE001 -- a missing table is a normal state here
        # The projection tables are new. An older database simply does not have
        # them, and that has to degrade to "no engine projections" rather than
        # taking the whole draft down -- the board still has Sleeper's numbers.
        log.warning("Could not read projection_sets (%s). Falling back to stored points.", error)
        return None
    finally:
        connection.close()

    return row[0] if row else None


def load_inputs(set_id: int) -> tuple[ProjectionInputs, Dict[tuple, str]]:
    """Engine inputs for a set, plus the map from player to `sleeper_id`."""
    if set_id in _INPUT_CACHE:
        return _INPUT_CACHE[set_id], _ID_CACHE[set_id]

    connection = data_service.get_db_connection()
    if connection is None:
        raise RuntimeError("Could not connect to the database.")

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT team, plays, pass_pct, rush_ypc FROM projection_teams WHERE set_id = %s",
                (set_id,),
            )
            volumes = {
                row[0]: TeamVolume(team=row[0], plays=row[1], pass_pct=row[2], rush_ypc=row[3] or 0.0)
                for row in cursor.fetchall()
            }

            cursor.execute(
                """
                SELECT team, player_key, display_name, pos, sleeper_id,
                       w_pass, w_rush, w_tgt,
                       comp_pct, yds_per_comp, pass_td_pct, int_pct,
                       rush_ypc, rush_td_rate,
                       catch_rate, yds_per_rec, rec_td_rate
                FROM projection_players
                WHERE set_id = %s
                ORDER BY team, player_key
                """,
                (set_id,),
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    players: List[PlayerRates] = []
    ids: Dict[tuple, str] = {}
    for row in rows:
        team, key, name, pos, sleeper_id = row[0], row[1], row[2], row[3], row[4]
        rates = row[5:]
        players.append(PlayerRates(
            team=team, key=key, name=name, pos=pos,
            **dict(zip(
                (
                    'w_pass', 'w_rush', 'w_tgt',
                    'comp_pct', 'yds_per_comp', 'pass_td_pct', 'int_pct',
                    'rush_ypc', 'rush_td_rate',
                    'catch_rate', 'yds_per_rec', 'rec_td_rate',
                ),
                (float(value or 0.0) for value in rates),
            )),
        ))
        if sleeper_id:
            ids[(team, key)] = sleeper_id

    inputs = ProjectionInputs(volumes=volumes, players=players)
    _INPUT_CACHE[set_id] = inputs
    _ID_CACHE[set_id] = ids
    log.info(
        "Loaded projection set %d: %d players across %d teams, %d with a sleeper_id.",
        set_id, len(players), len(volumes), len(ids),
    )
    return inputs, ids


def projected_points(
    scoring: ScoringSettings, set_id: int | None = None
) -> pd.Series:
    """
    Projected season points per `sleeper_id`, under the league's own scoring.

    Returns an empty Series when there is no projection set, which is the state
    an older database is in. Callers fall back to the stored per-format columns.

    Players with no `sleeper_id` are dropped only here, at the very end. They are
    projected first, because their share weights are part of their team's
    denominators -- removing them earlier would inflate every teammate's share.
    """
    if set_id is None:
        set_id = active_set_id()
    if set_id is None:
        return pd.Series(dtype=float)

    inputs, ids = load_inputs(set_id)

    points: Dict[str, float] = {}
    for player in project_all(inputs, scoring):
        sleeper_id = ids.get((player.team, player.key))
        if sleeper_id is not None:
            points[sleeper_id] = player.points

    return pd.Series(points, dtype=float)


def clear_cache() -> None:
    """Drops cached inputs. For tests, and for a re-import inside a live process."""
    _INPUT_CACHE.clear()
    _ID_CACHE.clear()
