
import pytest
import numpy as np
import pandas as pd
from backend.services import simulation_service
from backend.services.simulation_service import simulate_cpu_pick, calculate_draft_score
from backend.services.draft import Team

ROUNDS = 15


@pytest.fixture(autouse=True)
def _seeded_rng():
    """
    simulate_cpu_pick samples from the top 10 via np.random.choice, so the tests
    below were failing roughly one run in eight. Seed it so they are reproducible.
    """
    np.random.seed(0)


def create_test_player_df():
    """Creates a sample DataFrame of players for testing."""
    data = {
        'display_name': ['Player A', 'Player B', 'Player C', 'Player D', 'Player E'],
        'pos': ['QB', 'RB', 'WR', 'TE', 'RB'],
        'VORP': [120, 100, 110, 90, 95], # Player A has highest VORP
        'ADP': [1, 20, 15, 30, 25]      # Player A has best ADP
    }
    return pd.DataFrame(data)

def test_calculate_draft_score():
    """Tests the calculate_draft_score function."""
    players = create_test_player_df()
    scored_players = calculate_draft_score(players)
    assert 'draft_score' in scored_players.columns
    # Player A (ADP 1) should have the best (lowest) score.
    assert scored_players.sort_values('draft_score').iloc[0]['display_name'] == 'Player A'

def test_simulate_cpu_pick():
    """Tests the simulate_cpu_pick function."""
    available_players = create_test_player_df()
    team = Team()

    # With an empty team, the CPU should pick the best player available (BPA).
    # Based on draft_score, Player A should be the top choice.
    picks = [simulate_cpu_pick(available_players, team, ROUNDS) for _ in range(10)]
    assert 'Player A' in picks

    # Test with positional need
    team.add_player("Some QB", "QB")
    team.add_player("Some TE", "TE")
    # Now the team needs an RB or WR. Player B (RB) and C (WR) are top options.
    picks_with_need = [simulate_cpu_pick(available_players, team, ROUNDS) for _ in range(20)]
    assert 'Player B' in picks_with_need or 'Player C' in picks_with_need


def test_position_counts_do_not_depend_on_the_name_form():
    """
    The tally is keyed off the position passed to add_player, not off a lookup.

    draft_manager_service adds normalized names ("josh_allen") while the VONA
    simulation added display names ("Josh Allen"); the old DataFrame lookup matched
    on display_name and so returned 0 for the real draft every time.
    """
    team = Team()
    team.add_player("josh_allen", "QB")
    team.add_player("Jayden Daniels", "QB")

    assert team.count_players_at_position('QB') == 2
    assert team.count_players_at_position('RB') == 0


def test_third_quarterback_is_penalised():
    """The QB penalty is the reason count_players_at_position exists."""
    available_players = create_test_player_df()

    empty = Team()
    loaded = Team()
    loaded.add_player("qb_one", "QB")
    loaded.add_player("qb_two", "QB")

    np.random.seed(0)
    from_empty = [simulate_cpu_pick(available_players, empty, ROUNDS) for _ in range(30)]
    np.random.seed(0)
    from_loaded = [simulate_cpu_pick(available_players, loaded, ROUNDS) for _ in range(30)]

    # Player A is the QB, and the best player on the board by both VORP and ADP.
    # The penalty is a weighting, not a veto, so compare rates rather than demanding
    # the CPU never takes him.
    assert from_empty.count('Player A') > from_loaded.count('Player A')


def test_counts_survive_a_roster_overflow():
    """
    DEFAULT_ROUNDS is 20 against an 18-slot roster, so add_player runs out of room.

    A player with nowhere to sit is still a player the team drafted, and the QB
    penalty has to see them.
    """
    team = Team(roster=["QB1"])
    team.add_player("starter", "QB")
    team.add_player("backup", "QB")
    team.add_player("third_stringer", "QB")

    assert team.roster == {"QB1": "starter"}
    assert team.count_players_at_position('QB') == 3


def test_copy_is_detached_but_carries_the_roster():
    team = Team()
    team.add_player("drafted_rb", "RB")

    clone = team.copy()
    assert clone.count_players_at_position('RB') == 1
    assert "drafted_rb" in clone.roster.values()

    clone.add_player("another_rb", "RB")
    assert team.count_players_at_position('RB') == 1, "the original must not move"
    assert clone.count_players_at_position('RB') == 2


def late_board():
    """
    A board as it looks once the top is gone: the kicker and defense hold the best
    ADP left, which is exactly why they need an explicit brake.
    """
    return pd.DataFrame({
        'display_name': ['Elite DEF', 'Elite K', 'Weak DEF', 'Weak K', 'Bench RB'],
        'pos':          ['DEF',       'K',       'DEF',      'K',      'RB'],
        'VORP':         [20.0,        13.0,      -24.0,      -97.0,    -30.0],
        'ADP':          [119.0,       159.0,     280.0,      300.0,    240.0],
        'draft_score':  [1.0,         2.0,       4.0,        5.0,      3.0],
    })


def scores_after_penalty(team, rounds_remaining):
    board = late_board()
    simulation_service._apply_late_round_penalty(
        board, 'draft_score', team, rounds_remaining
    )
    return dict(zip(board['display_name'], board['draft_score']))


def team_with(picks_made=0, **positions):
    team = Team()
    for pos, n in positions.items():
        for i in range(n):
            team.add_player(f"{pos}{i}", pos)
    for i in range(picks_made - team.picks_made):
        team.add_player(f"filler{i}", "RB")
    return team


@pytest.mark.parametrize("rounds_remaining", [15, 10, 5])
def test_kickers_and_defenses_are_pushed_down_while_the_bench_fills(rounds_remaining):
    scores = scores_after_penalty(Team(), rounds_remaining)

    assert scores['Elite DEF'] == 1.0 * simulation_service.LATE_ROUND_PENALTY
    assert scores['Elite K'] == 2.0 * simulation_service.LATE_ROUND_PENALTY
    assert scores['Bench RB'] == 3.0, "skill players are untouched"
    # The whole point: a below-replacement bench body now outranks a top defense.
    assert scores['Bench RB'] < scores['Elite DEF']


def test_the_best_one_left_gets_a_lighter_penalty_near_the_end():
    """'Only the most elite get picked before the final two rounds.'"""
    scores = scores_after_penalty(Team(), simulation_service.ELITE_WINDOW)

    assert scores['Elite DEF'] == pytest.approx(1.0 * simulation_service.ELITE_PENALTY)
    assert scores['Weak DEF'] == 4.0 * simulation_service.LATE_ROUND_PENALTY
    assert scores['Elite K'] == pytest.approx(2.0 * simulation_service.ELITE_PENALTY)
    assert scores['Weak K'] == 5.0 * simulation_service.LATE_ROUND_PENALTY


def test_one_round_earlier_there_is_no_exception():
    scores = scores_after_penalty(Team(), simulation_service.ELITE_WINDOW + 1)
    assert scores['Elite DEF'] == 1.0 * simulation_service.LATE_ROUND_PENALTY


def test_the_final_rounds_actively_prefer_an_unfilled_slot():
    """
    Otherwise teams finish the draft without a kicker -- 40 of 60 did when this was
    only a penalty that lifted, rather than a preference that turns on.
    """
    scores = scores_after_penalty(Team(), simulation_service.LATE_ROUND_GRACE)

    assert scores['Elite DEF'] == pytest.approx(1.0 * simulation_service.LATE_ROUND_BONUS)
    assert scores['Elite DEF'] < scores['Bench RB']


def test_a_position_already_filled_is_effectively_unpickable():
    """One K slot and one DEF slot, so a second is a wasted pick at any point."""
    scores = scores_after_penalty(team_with(picks_made=14, K=1), rounds_remaining=1)

    assert scores['Elite K'] == 2.0 * simulation_service.DUPLICATE_PENALTY
    assert scores['Elite DEF'] == pytest.approx(1.0 * simulation_service.LATE_ROUND_BONUS)
    assert scores['Elite DEF'] < scores['Bench RB'] < scores['Elite K']


def test_a_board_with_no_kickers_left_is_handled():
    board = late_board()
    board = board[board['pos'] == 'RB'].copy()
    simulation_service._apply_late_round_penalty(board, 'draft_score', Team(), 5)
    assert board['draft_score'].tolist() == [3.0]


def test_the_brake_reads_the_teams_own_roster():
    """No fifth copy of the snake-order arithmetic."""
    assert Team().picks_made == 0
    assert team_with(picks_made=7).picks_made == 7

    overflowed = Team(roster=["QB1"])
    for i in range(4):
        overflowed.add_player(f"p{i}", "QB")
    assert overflowed.picks_made == 4, "players with no free slot still count"


def deep_late_board(bench=15):
    """
    late_board() plus a real bench pool.

    simulate_cpu_pick samples from the ten best scores, so a board of five players
    reaches everything on it no matter what the scores are. Any test of the sampled
    path needs more than ten alternatives to be meaningful.
    """
    rows = [
        {'display_name': 'Elite DEF', 'pos': 'DEF', 'VORP': 20.0, 'ADP': 119.0},
        {'display_name': 'Elite K', 'pos': 'K', 'VORP': 13.0, 'ADP': 159.0},
    ]
    rows += [
        {'display_name': f"Bench{i}", 'pos': 'RB', 'VORP': -30.0 - i, 'ADP': 200.0 + i}
        for i in range(bench)
    ]
    return pd.DataFrame(rows)


def test_end_to_end_a_defense_loses_to_bench_bodies_mid_draft():
    """The sampled path, not just the scoring: 8 rounds left, so nothing K/DEF."""
    team = team_with(picks_made=7)
    picks = {simulate_cpu_pick(deep_late_board(), team, ROUNDS) for _ in range(40)}

    assert not picks & {'Elite DEF', 'Elite K'}, picks


def test_end_to_end_the_last_round_takes_the_defense():
    """
    And at the end it flips: the empty slot beats another bench body.

    simulate_cpu_pick gives its top choice 60% and spreads the rest, so this is a
    claim about which player leads, not one the sampling can ever make absolute.
    """
    team = team_with(picks_made=ROUNDS - 1)
    picks = [simulate_cpu_pick(deep_late_board(), team, ROUNDS) for _ in range(50)]
    counts = pd.Series(picks).value_counts()

    assert counts.idxmax() == 'Elite DEF'
    assert counts['Elite DEF'] > len(picks) / 2
