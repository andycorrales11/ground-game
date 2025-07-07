import pandas as pd
from pathlib import Path

'''
Value Over Replacement Player (VORP) Service
This service calculates the VORP for NFL players based on their seasonal stats.
It uses the seasonal stats data and the amount of users in the league to compute the VORP for each player.
'''

default_roster_pos = ["QB","RB","RB","WR","WR","TE","FLEX","FLEX","K","DEF","BN","BN","BN","BN","BN","BN","BN","BN","BN","BN"]

def calculate_vorp(df : pd.DataFrame, pos : str, roster = default_roster_pos, teams = 12, format = 'STD' ) -> pd.DataFrame:
    replacement_index = roster.count(pos) * teams
    match format:
        case 'HalfPPR':
            print("HalfPPR VORP currently not available")
            return df 
        case 'STD':
            points_column = "fantasy_points"
        case 'PPR':
            points_column = "fantasy_points_ppr"
    df = df.dropna(subset=["display_name"])
    df = df.sort_values(by=points_column, ascending=False)
    baseline = df.head(replacement_index + 1).iloc[replacement_index]
    df["vorp"] = df[points_column] - baseline[points_column]

    return df

def calculate_vona(df : pd.DataFrame, pos : str, teams = 12, format = 'STD') -> pd.DataFrame:
    pass

"""
Ex Baselines:
QB: QB12
RB: RB24 + Flex (8/24) = RB32
WR: WR24 + Flex (16/24) = WR40
TE: TE12
Flex: RB32 / WR40
"""
