
import pytest
import numpy as np
import pandas as pd
from backend.services.simulation_service import simulate_cpu_pick, calculate_draft_score
from backend.services.draft import Team


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
    picks = [simulate_cpu_pick(available_players, team) for _ in range(10)]
    assert 'Player A' in picks

    # Test with positional need
    team.add_player("Some QB", "QB")
    team.add_player("Some TE", "TE")
    # Now the team needs an RB or WR. Player B (RB) and C (WR) are top options.
    picks_with_need = [simulate_cpu_pick(available_players, team) for _ in range(20)]
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
    from_empty = [simulate_cpu_pick(available_players, empty) for _ in range(30)]
    np.random.seed(0)
    from_loaded = [simulate_cpu_pick(available_players, loaded) for _ in range(30)]

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
