"""
Tests for the VONA calculation.

This file previously held a print-based script that hit the live database, called
calculate_vona with the wrong number of arguments, and filtered on a 'position'
column that does not exist. It is now a real test against a synthetic board, so it
runs without a database.
"""
import numpy as np
import pytest

from backend.services.vbd_service import calculate_vona_board, simulate_to_next_turn
from backend.services.draft import Draft, Team
from backend.tests.boards import make_board


@pytest.fixture(autouse=True)
def _seeded_rng():
    """simulate_cpu_pick samples randomly; seed so these assertions are stable."""
    np.random.seed(0)


def make_draft(board, teams=12):
    return Draft(board.copy(), 'PPR', teams, 15, order='snake'), [Team() for _ in range(teams)]


def test_no_intervening_picks_means_zero_vona():
    """If you pick again immediately, waiting costs nothing."""
    board = make_board()
    draft, teams = make_draft(board)

    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=0,
                                current_pick=0)

    assert set(vona) == set(board['display_name'])
    assert all(v == 0.0 for v in vona.values())


def test_vona_is_gap_to_best_survivor_at_position():
    """VONA is the candidate's projection minus the best left at their position."""
    board = make_board()
    draft, teams = make_draft(board)

    survivors = simulate_to_next_turn(draft, teams, picks_to_simulate=11,
                                      current_pick=0)
    best_rb = survivors[survivors['pos'] == 'RB']['fantasy_points_ppr'].max()

    # One run, so the shared simulation is the only source of randomness.
    np.random.seed(0)
    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                current_pick=0, runs=1)

    rb1_points = board.loc[board['display_name'] == 'RB1', 'fantasy_points_ppr'].iloc[0]
    assert vona['RB1'] == pytest.approx(max(0.0, rb1_points - best_rb))


def test_vona_is_never_negative():
    board = make_board()
    draft, teams = make_draft(board)

    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                current_pick=0)

    assert vona, "expected a populated VONA board"
    assert all(v >= 0.0 for v in vona.values())
    assert not any(np.isnan(v) for v in vona.values())


def test_unprojected_players_score_zero():
    """Kickers have no projection, so they must not produce NaN."""
    board = make_board()
    draft, teams = make_draft(board)

    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                current_pick=0)

    assert vona['K1'] == 0.0
    assert vona['K2'] == 0.0


def test_scores_every_available_player():
    """The old implementation capped this at the top 50 by ADP for performance."""
    board = make_board(per_pos=20)
    draft, teams = make_draft(board)

    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                current_pick=0)

    assert len(vona) == len(board) > 50


def test_simulation_does_not_mutate_the_caller_state():
    """simulate_to_next_turn must leave the real draft untouched."""
    board = make_board()
    draft, teams = make_draft(board)

    simulate_to_next_turn(draft, teams, picks_to_simulate=11, current_pick=0)

    assert draft.drafted_players == set()
    assert all(slot is None for team in teams for slot in team.roster.values())
    assert all(team.count_players_at_position(pos) == 0
               for team in teams for pos in ('QB', 'RB', 'WR', 'TE'))


def test_simulation_starts_from_the_rosters_already_built():
    """
    The forward simulation must inherit each opponent's real roster.

    It used to construct its teams with Team(roster=t.roster.copy()), which copies
    the slot *names* only -- so every simulated opponent began with an empty roster
    and drafted as though it were round one, regardless of how far along the draft
    actually was.
    """
    board = make_board()
    total_qbs = (board['pos'] == 'QB').sum()

    def qbs_taken(already_have_two: bool) -> int:
        np.random.seed(0)  # Same random stream on both sides of the comparison.
        draft, teams = make_draft(board)
        if already_have_two:
            for i, team in enumerate(teams):
                team.add_player(f"incumbent_qb_a{i}", 'QB')
                team.add_player(f"incumbent_qb_b{i}", 'QB')
        survivors = simulate_to_next_turn(draft, teams, picks_to_simulate=11,
                                          current_pick=0)
        return total_qbs - (survivors['pos'] == 'QB').sum()

    # QBs carry the highest projections on this board, so opponents starting from
    # scratch reach for them. Opponents who already hold two should not.
    assert qbs_taken(already_have_two=True) < qbs_taken(already_have_two=False)


def test_top_player_at_a_run_position_outranks_a_deep_one():
    """A scarce elite player should carry more VONA than a replaceable one."""
    board = make_board()
    draft, teams = make_draft(board)

    vona = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                current_pick=0)

    assert vona['RB1'] > vona['RB12']
