# python -m backend.tests.vorp_test
import pandas as pd
from pathlib import Path
from backend.services.vorp_service import calculate_vorp

DATA_DIR = Path("data/nfl_stats/nfl_stats_wrs_2024.parquet")

def main():
    print("start")
    df = pd.read_parquet(DATA_DIR)
    df = calculate_vorp(df, 'WR')
    print(df.head(25)[['display_name', 'vorp']])

if __name__ == "__main__":
    main()   
