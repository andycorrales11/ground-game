# python -m backend.tests.vorp_test
import pandas as pd
from backend.services.vbd_service import create_vbd_big_board

def main() -> None:
    print("start")
    formats_to_test = ['STD', 'HalfPPR', 'PPR']

    for format_type in formats_to_test:
        print(f"\n--- Testing VORP Big Board for {format_type} Format ---")
        big_board_df = create_vbd_big_board(format=format_type)

        if big_board_df is not None and not big_board_df.empty:
            # Filter for Wide Receivers and print relevant columns
            wr_df = big_board_df[big_board_df['position'] == 'WR'].copy()
            wr_df.sort_values(by='VORP', ascending=False, inplace=True)
            print(wr_df.head(25)[['display_name', 'VORP', 'ADP']])
        else:
            print(f"Failed to create VBD big board or it is empty for {format_type} format.")

if __name__ == "__main__":
    main()   
