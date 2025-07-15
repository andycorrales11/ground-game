import pandas as pd
import numpy as np
from backend.services.vbd_service import calculate_vona
from backend.services.draft import Draft, Team

def create_test_df():
    """Creates a sample DataFrame for testing."""
    data = {
        'player_id': [1, 2, 3, 4, 5],
        'display_name': ['Player A', 'Player B', 'Player C', 'Player D', 'Player E'],
        'position': ['WR', 'WR', 'WR', 'WR', 'WR'],
        'fantasy_points_ppr': [200, 180, 150, 140, 100],
        'VORP': [80, 60, 30, 20, -20] # Add VORP for simulation logic
    }
    return pd.DataFrame(data)

def test_calculate_vona():
    """
    Tests the calculate_vona function.
    This is a basic test to ensure the function runs and returns a float.
    A full integration test would be very complex due to the draft simulation.
    """
    players = create_test_df()
    # The draft needs a full player list with all positions for VORP calcs in the sim
    full_player_data = {
        'player_id': range(20),
        'display_name': [f'Player {i}' for i in range(20)],
        'position': ['QB']*5 + ['RB']*5 + ['WR']*5 + ['TE']*5,
        'fantasy_points_ppr': [300-i*10 for i in range(20)],
        'VORP': [100-i*5 for i in range(20)]
    }
    full_players_df = pd.DataFrame(full_player_data)

    draft = Draft(full_players_df, 'PPR', 12, 16)
    teams = [Team() for _ in range(12)]
    
    player_to_eval = players.iloc[0] # Player A
    
    # Simulate with 4 picks between user's turns
    vona = calculate_vona(player_to_eval, draft, teams, 4, 12, 1, 'snake')
    
    assert isinstance(vona, np.number)
    # In this controlled scenario, VONA should be positive as Player A is the best WR
    assert vona >= 0

    print("VONA calculation test passed (basic check).")

if __name__ == "__main__":
    test_calculate_vona()
