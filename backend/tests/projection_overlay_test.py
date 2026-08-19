"""
Tests for the hybrid board: engine projections over stored ones.

The board has two sources of points and always will. The projection engine
models skill positions and nothing else, so kickers, defenses, and the deep pool
keep the per-format numbers the database has always held. What must never happen
is the seam swallowing anyone -- a player the engine does not cover has to come
through with his stored projection intact, not a zero and not a NaN.
"""
import pandas as pd
import pytest

from backend import league
from backend.services import vbd_service


@pytest.fixture
def board():
    return pd.DataFrame([
        {'sleeper_id': '1', 'display_name': 'Engine QB', 'pos': 'QB', 'fantasy_points_ppr': 100.0},
        {'sleeper_id': '2', 'display_name': 'Engine WR', 'pos': 'WR', 'fantasy_points_ppr': 200.0},
        {'sleeper_id': '3', 'display_name': 'Deep WR', 'pos': 'WR', 'fantasy_points_ppr': 30.0},
        {'sleeper_id': '4', 'display_name': 'A Kicker', 'pos': 'K', 'fantasy_points_ppr': 120.0},
        {'sleeper_id': '5', 'display_name': 'A Defense', 'pos': 'DEF', 'fantasy_points_ppr': 90.0},
        {'sleeper_id': '6', 'display_name': 'Unprojected', 'pos': 'WR', 'fantasy_points_ppr': float('nan')},
    ])


def _with_engine_points(monkeypatch, points: dict):
    monkeypatch.setattr(
        vbd_service.projection_service,
        'projected_points',
        lambda scoring, set_id=None: pd.Series(points, dtype=float),
    )


def test_engine_points_replace_stored_ones_only_where_they_exist(monkeypatch, board):
    _with_engine_points(monkeypatch, {'1': 333.0, '2': 444.0})

    out = vbd_service._apply_engine_projections(
        board, 'fantasy_points_ppr', league.ScoringSettings()
    )
    points = out.set_index('sleeper_id')['fantasy_points_ppr']

    # Covered by the engine: replaced.
    assert points['1'] == 333.0
    assert points['2'] == 444.0

    # Not covered: the stored projection survives untouched. This is the whole
    # reason kickers and defenses are still on the board with a real value.
    assert points['3'] == 30.0
    assert points['4'] == 120.0
    assert points['5'] == 90.0

    # And an unprojected player stays unprojected -- NaN, not 0.0, because 0 is a
    # real and fairly good score that would sort him above everyone below
    # replacement level.
    assert pd.isna(points['6'])


def test_no_active_projection_set_leaves_the_board_alone(monkeypatch, board):
    """
    An older database has no projection tables at all. That has to degrade to the
    stored projections rather than emptying the board.
    """
    _with_engine_points(monkeypatch, {})

    out = vbd_service._apply_engine_projections(
        board.copy(), 'fantasy_points_ppr', league.ScoringSettings()
    )

    pd.testing.assert_series_equal(
        out['fantasy_points_ppr'], board['fantasy_points_ppr'], check_names=False
    )


def test_a_failing_projection_lookup_does_not_take_the_draft_down(monkeypatch, board):
    def explode(scoring, set_id=None):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(vbd_service.projection_service, 'projected_points', explode)

    out = vbd_service._apply_engine_projections(
        board.copy(), 'fantasy_points_ppr', league.ScoringSettings()
    )

    pd.testing.assert_series_equal(
        out['fantasy_points_ppr'], board['fantasy_points_ppr'], check_names=False
    )


def test_a_board_without_sleeper_ids_is_left_alone(monkeypatch, board):
    """Engine projections join on sleeper_id; with no column there is no join."""
    _with_engine_points(monkeypatch, {'1': 333.0})
    without_ids = board.drop(columns=['sleeper_id'])

    out = vbd_service._apply_engine_projections(
        without_ids.copy(), 'fantasy_points_ppr', league.ScoringSettings()
    )

    pd.testing.assert_series_equal(
        out['fantasy_points_ppr'], without_ids['fantasy_points_ppr'], check_names=False
    )
