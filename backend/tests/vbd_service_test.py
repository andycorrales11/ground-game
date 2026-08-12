"""
Tests for VORP.

The distinction under test throughout: VORP 0 means "exactly replacement level",
which is a real and perfectly useful player. It must never also mean "we have no
projection for this person" -- 0 sorts above every below-replacement player, so
conflating the two floats the unknowns to the top of the board.
"""
import numpy as np
import pandas as pd
import pytest

from backend import config
from backend.services.vbd_service import calculate_vorp


def board(points_by_pos):
    """points_by_pos: {'RB': [200, 180, None, ...]}"""
    rows = []
    for pos, points in points_by_pos.items():
        for i, pts in enumerate(points):
            rows.append({
                'display_name': f"{pos}{i + 1}",
                'pos': pos,
                'fantasy_points_ppr': np.nan if pts is None else float(pts),
            })
    return pd.DataFrame(rows)


def test_unprojected_players_get_nan_not_zero():
    """
    A player with no projection is unranked, not replacement level.

    This was 163 players on the real 2026 board -- every kicker and defense plus
    ~78 unprojected skill players, all pinned at 0.0 and therefore sorting above
    every genuine below-replacement player.
    """
    df = board({'RB': [300, 250, 200, None, 150]})
    out = calculate_vorp(df, 'RB', teams=1, format='PPR')

    assert out.loc[out['display_name'] == 'RB4', 'VORP'].isna().all()
    assert out['VORP'].notna().sum() == 4


def test_unprojected_players_sort_to_the_bottom():
    """The point of NaN over 0: a real negative VORP must outrank an unknown."""
    df = board({'RB': [300, 250, 200, None, 150]})
    out = calculate_vorp(df, 'RB', teams=1, format='PPR')

    ordered = out.sort_values('VORP', ascending=False)['display_name'].tolist()
    assert ordered[-1] == 'RB4'
    assert ordered.index('RB5') < ordered.index('RB4')


def test_replacement_level_player_scores_exactly_zero():
    """The other half of the distinction: 0 still has to mean replacement level."""
    # teams=2, one RB slot, no FLEX -> replacement is the 3rd RB (index 2).
    df = board({'RB': [300, 250, 200, 150]})
    out = calculate_vorp(df, 'RB', teams=2, format='PPR',
                         roster_config=['RB', 'BN'])

    scores = dict(zip(out['display_name'], out['VORP']))
    assert scores['RB3'] == pytest.approx(0.0)
    assert scores['RB1'] == pytest.approx(100.0)
    assert scores['RB4'] == pytest.approx(-50.0)


def test_kickers_and_defenses_are_in_scope_now():
    """
    They were excluded while the Athletic CSVs were the projection source, because
    those files never covered K or DEF. Sleeper does.
    """
    assert 'K' in config.VORP_POSITIONS
    assert 'DEF' in config.VORP_POSITIONS

    df = board({'K': [160, 150, 140, 120]})
    out = calculate_vorp(df, 'K', teams=1, format='PPR')

    assert out['VORP'].notna().all()
    assert out['VORP'].nunique() > 1, "kickers must not all collapse to one value"


def test_a_position_with_fewer_players_than_slots_still_resolves():
    """No replacement player exists, so VORP falls back to raw points."""
    df = board({'TE': [200, 180]})
    out = calculate_vorp(df, 'TE', teams=12, format='PPR')

    assert out['VORP'].tolist() == pytest.approx([200.0, 180.0])


def test_positions_never_computed_stay_nan():
    """The stray DT the ADP files carry must not read as replacement level."""
    df = board({'RB': [300, 200], 'DT': [10]})
    out = calculate_vorp(df, 'RB', teams=1, format='PPR')

    assert out.loc[out['pos'] == 'DT', 'VORP'].isna().all()


def test_an_unknown_format_is_rejected():
    with pytest.raises(ValueError):
        calculate_vorp(board({'RB': [100]}), 'RB', format='Superflex')
