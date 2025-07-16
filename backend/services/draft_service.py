import pandas as pd
from backend import config

def get_user_picks(pick: int, order: str = 'snake', teams: int = config.DEFAULT_TEAMS, rounds: int = config.DEFAULT_ROUNDS) -> list[int]:
    """
    Calculates the pick numbers for the user in a draft.
    """
    user_picks = []
    for i in range(rounds):
        if order == 'snake' and i % 2 != 0:
            user_picks.append((i * teams) + (teams - pick + 1))
        else:
            user_picks.append((i * teams) + pick)
    return user_picks


