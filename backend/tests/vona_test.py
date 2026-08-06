"""
Tests for the VONA calculation.

This file previously held a print-based script that hit the live database, called
calculate_vona with the wrong number of arguments, and filtered on a 'position'
column that does not exist. It is now a real test against a synthetic board, so it
runs without a database.
"""
import numpy as np
import pandas as pd
import pytest

from backend.services.vbd_service import calculate_vona_board, simulate_to_next_turn
from backend.services.draft import Draft, Team


@pytest.fixture(autouse=True)
def _seeded_rng():
    """simulate_cpu_pick samples randomly; seed so these assertions are stable."""
    np.random.seed(0)


def make_board(per_pos=12):
    """
    A board with a clear talent gradient at each position.

    ADP interleaves the positions, as a real board does -- if one position swept
    the top of the ADP list, every simulated pick would come from it and the other
    positions would never be touched.
    """
    by_pos = {}
    for pos, base in (('RB', 280), ('WR', 270), ('QB', 300), ('TE', 200)):
        by_pos[pos] = [
            {
                'display_name': f"{pos}{i + 1}",
                'normalized_name': f"{pos}{i + 1}".lower(),
                'pos': pos,
                'team': 'FA',
                'VORP': float(base - i * 10),
                'fantasy_points_ppr': float(base - i * 10),
            }
            for i in range(per_pos)
        ]

    rows = []
    for i in range(per_pos):
        for pos in ('RB', 'WR', 'QB', 'TE'):
            rows.append(by_pos[pos][i])

    # Kickers carry no projection, which is what the real board looks like.
    for i in range(3):
        name = f"K{i + 1}"
        rows.append({
            'display_name': name,
            'normalized_name': name.lower(),
            'pos': 'K',
            'team': 'FA',
            'VORP': 0.0,
            'fantasy_points_ppr': np.nan,
        })

    board = pd.DataFrame(rows)
    board['ADP'] = range(1, len(board) + 1)
    return board


def make_draft(board, teams=12):
    return Draft(board.copy(), 'PPR', teams, 15, order='snake'), [Team() for _ in range(teams)]


def test_no_intervening_picks_means_zero_vona():
    """If you pick again immediately, waiting costs nothing."""
    board = make_board()
    draft, teams = make_draft(board)

    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=0,
                                current_pick=0, full_player_df=board)

    assert set(vona) == set(board['display_name'])
    assert all(v == 0.0 for v in vona.values())


def test_vona_is_gap_to_best_survivor_at_position():
    """VONA is the candidate's projection minus the best left at their position."""
    board = make_board()
    draft, teams = make_draft(board)

    survivors = simulate_to_next_turn(draft, teams, picks_to_simulate=11,
                                      current_pick=0, full_player_df=board)
    best_rb = survivors[survivors['pos'] == 'RB']['fantasy_points_ppr'].max()

    # One run, so the shared simulation is the only source of randomness.
    np.random.seed(0)
    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                current_pick=0, full_player_df=board, runs=1)

    rb1_points = board.loc[board['display_name'] == 'RB1', 'fantasy_points_ppr'].iloc[0]
    assert vona['RB1'] == pytest.approx(max(0.0, rb1_points - best_rb))


def test_vona_is_never_negative():
    board = make_board()
    draft, teams = make_draft(board)

    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                current_pick=0, full_player_df=board)

    assert vona, "expected a populated VONA board"
    assert all(v >= 0.0 for v in vona.values())
    assert not any(np.isnan(v) for v in vona.values())


def test_unprojected_players_score_zero():
    """Kickers have no projection, so they must not produce NaN."""
    board = make_board()
    draft, teams = make_draft(board)

    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                current_pick=0, full_player_df=board)

    assert vona['K1'] == 0.0
    assert vona['K2'] == 0.0


def test_scores_every_available_player():
    """The old implementation capped this at the top 50 by ADP for performance."""
    board = make_board(per_pos=20)
    draft, teams = make_draft(board)

    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                current_pick=0, full_player_df=board)

    assert len(vona) == len(board) > 50


def test_simulation_does_not_mutate_the_caller_state():
    """simulate_to_next_turn must leave the real draft untouched."""
    board = make_board()
    draft, teams = make_draft(board)

    simulate_to_next_turn(draft, teams, picks_to_simulate=11,
                          current_pick=0, full_player_df=board)

    assert draft.drafted_players == set()
    assert all(slot is None for team in teams for slot in team.roster.values())


def test_top_player_at_a_run_position_outranks_a_deep_one():
    """A scarce elite player should carry more VONA than a replaceable one."""
    board = make_board()
    draft, teams = make_draft(board)

    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                current_pick=0, full_player_df=board)

    assert vona['RB1'] > vona['RB12']
