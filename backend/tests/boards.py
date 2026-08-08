"""
Synthetic draft boards for tests.

Shared so that tests exercising the draft manager and the VONA calculation agree on
what a board looks like, and so neither of them needs a database.
"""
import numpy as np
import pandas as pd


def make_board(per_pos=12):
    """
    A board with a clear talent gradient at each position.

    ADP interleaves the positions, as a real board does -- if one position swept
    the top of the ADP list, every simulated pick would come from it and the other
    positions would never be touched.
    """
    by_pos = {}
    for pos, base in (('RB', 280), ('WR', 270), ('QB', 300), ('TE', 200)):
        by_pos[pos] = [
            {
                'display_name': f"{pos}{i + 1}",
                'normalized_name': f"{pos}{i + 1}".lower(),
                'pos': pos,
                'team': 'FA',
                'VORP': float(base - i * 10),
                'fantasy_points_ppr': float(base - i * 10),
            }
            for i in range(per_pos)
        ]

    rows = []
    for i in range(per_pos):
        for pos in ('RB', 'WR', 'QB', 'TE'):
            rows.append(by_pos[pos][i])

    # Kickers carry no projection, which is what the real board looks like.
    for i in range(3):
        name = f"K{i + 1}"
        rows.append({
            'display_name': name,
            'normalized_name': name.lower(),
            'pos': 'K',
            'team': 'FA',
            'VORP': 0.0,
            'fantasy_points_ppr': np.nan,
        })

    board = pd.DataFrame(rows)
    board['ADP'] = range(1, len(board) + 1)
    return board
