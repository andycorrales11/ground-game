"""
Tests for the superflex ADP column and how the board falls back off it.

Two separate claims are under test.

The first is selection: a lineup with an SFLEX slot drafts off `superflex_adp`,
and a lineup without one must not, because the two columns disagree violently
about quarterbacks and that is the entire point of having both.

The second is the seam. The export covers the top 270 players, so kickers,
defenses and the deep pool fall back to the format column -- and that is a
deliberate choice rather than an oversight, because the export lists no kickers
or defenses at all and any correction measured off it would be circular. The
tests pin the fallback down so the choice cannot be quietly reversed.
"""
import numpy as np
import pandas as pd
import pytest

from backend import league
from backend.services import vbd_service


@pytest.fixture
def board():
    """
    A miniature 2026-shaped board.

    The quarterbacks jump (25 -> 3, 45 -> 8) and everyone else drifts back by
    roughly 15 to make room. The kicker and the two deep receivers are the
    uncovered case: a real format ADP, no superflex ADP.
    """
    return pd.DataFrame([
        {'display_name': 'Elite QB',   'pos': 'QB', 'ppr_adp': 25.0,  'superflex_adp': 3.0},
        {'display_name': 'Good QB',    'pos': 'QB', 'ppr_adp': 45.0,  'superflex_adp': 8.0},
        {'display_name': 'Stud RB',    'pos': 'RB', 'ppr_adp': 1.0,   'superflex_adp': 1.5},
        {'display_name': 'Stud WR',    'pos': 'WR', 'ppr_adp': 10.0,  'superflex_adp': 22.0},
        {'display_name': 'Mid WR',     'pos': 'WR', 'ppr_adp': 60.0,  'superflex_adp': 78.0},
        {'display_name': 'Late RB',    'pos': 'RB', 'ppr_adp': 100.0, 'superflex_adp': 120.0},
        {'display_name': 'A Kicker',   'pos': 'K',  'ppr_adp': 130.0, 'superflex_adp': np.nan},
        {'display_name': 'Deep WR',    'pos': 'WR', 'ppr_adp': 200.0, 'superflex_adp': np.nan},
        {'display_name': 'Deeper WR',  'pos': 'WR', 'ppr_adp': 260.0, 'superflex_adp': np.nan},
        {'display_name': 'No ADP',     'pos': 'TE', 'ppr_adp': np.nan, 'superflex_adp': np.nan},
    ])


def adp(board, name):
    out = vbd_service._superflex_adp(board, board['ppr_adp'])
    return float(out[board['display_name'] == name].iloc[0])


def test_covered_players_keep_their_real_superflex_adp(board):
    """The column is authoritative wherever it exists. Nothing is rescaled."""
    assert adp(board, 'Elite QB') == 3.0
    assert adp(board, 'Good QB') == 8.0
    assert adp(board, 'Stud WR') == 22.0
    assert adp(board, 'Late RB') == 120.0


def test_an_uncovered_player_keeps_the_format_column(board):
    """
    The seam, asserted rather than left implicit.

    An earlier version rescaled these onto the superflex scale by measuring the
    drift between the two columns. It was wrong: the export lists no kickers and
    no defenses, so that drift partly measures their own absence from it. See
    `_superflex_adp` for the full reasoning.
    """
    assert adp(board, 'A Kicker') == 130.0
    assert adp(board, 'Deep WR') == 200.0


def test_the_uncovered_pool_keeps_its_own_order(board):
    """
    Their format ADP relative to each other is the only ranking evidence there is
    about players this deep, so nothing may reorder them.
    """
    assert adp(board, 'A Kicker') < adp(board, 'Deep WR') < adp(board, 'Deeper WR')


def test_a_player_with_no_adp_anywhere_stays_unranked(board):
    """NaN, not a filled-in number: he sorts last, which is where he belongs."""
    out = vbd_service._superflex_adp(board, board['ppr_adp'])
    assert out[board['display_name'] == 'No ADP'].isna().all()


def test_the_two_columns_are_not_blended_for_a_covered_player(board):
    """
    Where the export has an opinion it is the only opinion. A quarterback the
    field takes at 25.6 in PPR and 3.0 in superflex must come through at 3.0
    exactly -- averaging the two would be worse than either.
    """
    out = vbd_service._superflex_adp(board, board['ppr_adp'])
    covered = board['superflex_adp'].notna()

    pd.testing.assert_series_equal(
        out[covered], board.loc[covered, 'superflex_adp'], check_names=False
    )


# --- selection ---------------------------------------------------------------

@pytest.fixture
def stored_board(board):
    """The frame as `load_player_data` returns it, with the projection columns."""
    df = board.copy()
    df['normalized_name'] = df['display_name'].str.lower().str.replace(' ', '_')
    df['sleeper_id'] = [str(i) for i in range(len(df))]
    df['ppr_proj_pts'] = 100.0
    return df


def _big_board(monkeypatch, stored_board, roster):
    monkeypatch.setattr(
        vbd_service.data_service, 'load_player_data', lambda: stored_board.copy()
    )
    # The engine overlay is a separate concern with its own tests.
    monkeypatch.setattr(
        vbd_service.projection_service,
        'projected_points',
        lambda scoring, set_id=None: pd.Series(dtype=float),
    )
    return vbd_service.create_vbd_big_board(format='PPR', roster=roster)


def test_a_superflex_lineup_drafts_off_the_superflex_column(monkeypatch, stored_board):
    out = _big_board(monkeypatch, stored_board, league.RosterSettings(superflex=1))
    by_name = out.set_index('display_name')['ADP']

    assert by_name['Elite QB'] == 3.0
    assert by_name['Stud WR'] == 22.0


def test_a_normal_lineup_is_left_on_the_format_column(monkeypatch, stored_board):
    """
    The regression that matters in the other direction: one superflex league must
    not quietly move every other league's quarterbacks up 20 rounds.
    """
    out = _big_board(monkeypatch, stored_board, league.RosterSettings())
    by_name = out.set_index('display_name')['ADP']

    assert by_name['Elite QB'] == 25.0
    assert by_name['Stud WR'] == 10.0


def test_a_missing_column_falls_back_loudly(monkeypatch, stored_board, caplog):
    """
    A database that predates the column must still draft, but it must say so --
    silently serving PPR ADP to a superflex room makes quarterbacks look free.
    """
    without = stored_board.drop(columns=['superflex_adp'])

    out = _big_board(monkeypatch, without, league.RosterSettings(superflex=1))

    assert out.set_index('display_name')['ADP']['Elite QB'] == 25.0
    assert any(
        'superflex_adp' in record.message and 'ingest_to_db' in record.message
        for record in caplog.records
    )
