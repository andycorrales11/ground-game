# python -m backend.tests.vona_test
import pandas as pd
import numpy as np
from backend.services.vbd_service import calculate_vona

def create_test_df():
    """Creates a sample DataFrame for testing."""
    data = {
        'player_id': [1, 2, 3, 4, 5],
        'display_name': ['Player A', 'Player B', 'Player C', 'Player D', 'Player E'],
        'position': ['WR', 'WR', 'WR', 'WR', 'WR'],
        'fantasy_points_ppr': [200, 180, 150, 140, 100]
    }
    return pd.DataFrame(data)

def test_calculate_vona():
    """Tests the calculate_vona function."""
    df = create_test_df()
    df_vona = calculate_vona(df, 'WR', format='PPR')

    expected_vona = [20.0, 30.0, 10.0, 40.0, np.nan]
    
    assert 'VONA' in df_vona.columns, "VONA column not created"
    assert df_vona['VONA'].equals(pd.Series(expected_vona, name='VONA')), "VONA calculation is incorrect"

    print("VONA calculation test passed!")

if __name__ == "__main__":
    test_calculate_vona()
