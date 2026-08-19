"""
Tests for what waiting costs -- the column the board still calls VONA.

    cost = P(gone by your next turn) x (his points - the next man down's)

The tests that used to live here asserted the previous formula, which subtracted
the *best* survivor at the position from every candidate. That made the column a
per-position constant offset from the projection, and clamped all but a handful
of players to zero. Several of the properties below exist specifically to stop
either of those coming back.
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


def test_no_intervening_picks_means_nothing_can_be_lost():
    """If you pick again immediately, waiting costs nothing and nobody is gone."""
    board = make_board()
    draft, teams = make_draft(board)

    waiting = calculate_vona_board(board, draft, teams, picks_to_simulate=0,
                                   current_pick=0)

    assert set(waiting.cost) == set(board['display_name'])
    assert all(v == 0.0 for v in waiting.cost.values())
    assert all(v == 0.0 for v in waiting.gone.values())


def test_cost_is_the_drop_to_the_next_man_down_times_the_chance_of_losing_him():
    """
    The formula, checked against the simulation it came from.

    One run, so the survivor set is exactly what simulate_to_next_turn returns
    for the same seed.
    """
    board = make_board()
    draft, teams = make_draft(board)

    survivors = simulate_to_next_turn(draft, teams, picks_to_simulate=11,
                                      current_pick=0)
    rb1_points = board.loc[board['display_name'] == 'RB1', 'fantasy_points_ppr'].iloc[0]
    surviving_rbs = survivors[survivors['pos'] == 'RB']['fantasy_points_ppr']
    next_down = surviving_rbs[surviving_rbs < rb1_points].max()
    rb1_survived = 'rb1' in set(survivors['normalized_name'])

    np.random.seed(0)
    waiting = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                   current_pick=0, runs=1)

    expected_gone = 0.0 if rb1_survived else 1.0
    assert waiting.gone['RB1'] == pytest.approx(expected_gone)
    assert waiting.cost['RB1'] == pytest.approx(expected_gone * (rb1_points - next_down))


def test_the_column_is_not_a_constant_offset_from_the_projection():
    """
    The defect that motivated the rewrite.

    Subtracting the best survivor at a position gave every player at that
    position the same subtrahend, so `points - cost` was a single constant and
    the column ranked players exactly as the projection already did. Comparing
    against the next man *down* makes the subtrahend per-player.
    """
    board = make_board(per_pos=20)
    draft, teams = make_draft(board)

    waiting = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                   current_pick=0)

    rbs = board[board['pos'] == 'RB']
    offsets = {
        round(row.fantasy_points_ppr - waiting.cost[row.display_name], 6)
        for row in rbs.itertuples()
    }
    assert len(offsets) > 1, "cost is still a per-position constant offset"


def test_everyone_plausibly_gone_carries_a_cost():
    """
    A zero here means something different than it used to.

    The old clamp zeroed players purely for being below the best survivor at
    their position, which discarded real information: 7 non-zero values out of
    681 on a real board. Now a zero means only that the simulations never once
    took the player before your next turn, which is exactly the set you do not
    have to decide about. So the non-zero set should track how many picks are
    actually coming, not the size of the board.
    """
    picks_to_simulate = 11
    board = make_board(per_pos=20)
    draft, teams = make_draft(board)

    waiting = calculate_vona_board(board, draft, teams,
                                   picks_to_simulate=picks_to_simulate,
                                   current_pick=0)

    at_risk = [name for name, value in waiting.gone.items() if value > 0]
    assert len(at_risk) >= picks_to_simulate
    assert all(waiting.cost[name] > 0 for name in at_risk
               if board.loc[board['display_name'] == name, 'fantasy_points_ppr'].notna().all())


def test_risk_reorders_the_board_rather_than_echoing_the_projection():
    """
    The point of the whole exercise.

    The previous column ranked players within a position exactly as the
    projection did, so it could never tell you to take a worse player sooner.
    This one can: a lesser player who is about to be taken outranks a better one
    who will still be there.
    """
    board = make_board(per_pos=20)
    draft, teams = make_draft(board)

    waiting = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                   current_pick=0)

    ranked = board[board['fantasy_points_ppr'].notna()].sort_values(
        'fantasy_points_ppr', ascending=False
    )['display_name'].tolist()
    costs = [waiting.cost[name] for name in ranked]

    # Somewhere down the projection order, cost goes back up.
    assert any(
        later > earlier
        for earlier, later in zip(costs, costs[1:])
    ), "cost is monotone in projection, so it carries nothing new"


def test_cost_is_never_negative_and_never_nan():
    board = make_board()
    draft, teams = make_draft(board)

    waiting = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                   current_pick=0)

    assert waiting.cost, "expected a populated board"
    assert all(v >= 0.0 for v in waiting.cost.values())
    assert not any(np.isnan(v) for v in waiting.cost.values())
    # Non-negativity is structural here -- both factors are non-negative by
    # construction -- rather than the result of a clamp doing the work.
    assert all(0.0 <= v <= 1.0 for v in waiting.gone.values())


def test_unprojected_players_score_zero():
    """Kickers have no projection, so they must not produce NaN."""
    board = make_board()
    draft, teams = make_draft(board)

    waiting = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                   current_pick=0)

    assert waiting.cost['K1'] == 0.0
    assert waiting.cost['K2'] == 0.0


def test_scores_every_available_player():
    """The old implementation capped this at the top 50 by ADP for performance."""
    board = make_board(per_pos=20)
    draft, teams = make_draft(board)

    waiting = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                   current_pick=0)

    assert len(waiting.cost) == len(board) > 50
    assert len(waiting.gone) == len(board)


def test_a_player_nobody_will_take_costs_nothing_to_wait_on(monkeypatch):
    """
    The signal the previous formula could not carry.

    A player certain to survive costs nothing to wait on however good he is --
    which is the difference between "he is valuable" and "take him now".
    """
    board = make_board()
    draft, teams = make_draft(board)

    # Nobody picks, so everybody survives.
    monkeypatch.setattr(
        'backend.services.vbd_service.simulate_to_next_turn',
        lambda *args, **kwargs: board.copy(),
    )
    waiting = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                   current_pick=0)

    assert waiting.gone['RB1'] == 0.0
    assert waiting.cost['RB1'] == 0.0


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
    """A scarce elite player should cost more to wait on than a replaceable one."""
    board = make_board()
    draft, teams = make_draft(board)

    waiting = calculate_vona_board(board, draft, teams, picks_to_simulate=11,
                                   current_pick=0)

    assert waiting.cost['RB1'] > waiting.cost['RB12']
