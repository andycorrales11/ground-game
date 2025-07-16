
import pytest
import pandas as pd
from backend.services.simulation_service import simulate_cpu_pick, calculate_draft_score
from backend.services.draft import Team

def create_test_player_df():
    """Creates a sample DataFrame of players for testing."""
    data = {
        'display_name': ['Player A', 'Player B', 'Player C', 'Player D', 'Player E'],
        'position': ['QB', 'RB', 'WR', 'TE', 'RB'],
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
