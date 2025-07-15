import pandas as pd
import numpy as np
from backend.services.vbd_service import calculate_vona, create_vbd_big_board # Added create_vbd_big_board
from backend.services.draft import Draft, Team

def test_calculate_vona():
    """
    Tests the calculate_vona function using real data from create_vbd_big_board.
    """
    # Use real data for the draft simulation
    full_players_df = create_vbd_big_board(format='PPR')
    if full_players_df.empty:
        print("Skipping VONA test: create_vbd_big_board returned empty DataFrame.")
        return

    # Ensure no NaN fantasy points before starting simulation
    if full_players_df['fantasy_points_ppr'].isnull().any():
        print("Skipping VONA test: NaN values found in 'fantasy_points_ppr'.")
        return

    # Initialize draft and teams once outside the loop
    draft = Draft(full_players_df.copy(), 'PPR', 12, 16)
    teams = [Team() for _ in range(12)]

    # Loop through a selection of players to test VONA calculation
    # We'll take the top 50 players overall for broader coverage
    players_to_test = full_players_df.sort_values(by='VORP', ascending=False).head(50)

    for index, player_to_eval in players_to_test.iterrows():
        print(f"\n--- Testing VONA for {player_to_eval['display_name']} ({player_to_eval['position']}) ---")
        
        # No need to re-create draft and teams here, they persist

        # Simulate with a reasonable number of picks (e.g., 50) to deplete player pool
        vona = calculate_vona(player_to_eval, draft, teams, 50, 12, 1, 'snake')

        print(f"VONA calculated for {player_to_eval['display_name']}: {vona}")
        assert isinstance(vona, np.number), f"VONA is not a number for {player_to_eval['display_name']}: {vona}"
        assert not np.isnan(vona), f"VONA is NaN for {player_to_eval['display_name']}"
        # VONA can be negative for lower-tier players, so remove assert vona >= 0

    print("All VONA calculations tested (using real data).")

if __name__ == "__main__":
    test_calculate_vona()
