
import pandas as pd
import numpy as np
from .draft import Team

def calculate_positional_scarcity(players: pd.DataFrame) -> dict:
    """
    Calculates the VORP drop-off for each position to determine scarcity.
    """
    scarcity = {}
    for pos in ['QB', 'RB', 'WR', 'TE']:
        pos_players = players[players['position'] == pos].sort_values(by='VORP', ascending=False)
        if len(pos_players) > 1:
            # Scarcity is the VORP difference between the best and second-best player
            scarcity[pos] = pos_players.iloc[0]['VORP'] - pos_players.iloc[1]['VORP']
        else:
            scarcity[pos] = 0
    return scarcity

def calculate_draft_score(players: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates a blended draft score based on VORP and ADP ranks.
    """
    players = players.copy()
    # Create ranks for VORP (higher is better)
    players['vorp_rank'] = players['VORP'].rank(ascending=False, na_option='bottom')
    
    # Create ranks for ADP (lower is better)
    if 'ADP' in players.columns:
        # Fill missing ADP with a high number to rank them lower
        players['adp_rank'] = players['ADP'].fillna(999).rank(ascending=True, na_option='bottom')
        # Blend the two ranks, giving more weight to ADP
        players['draft_score'] = (0.10 * players['vorp_rank']) + (0.90 * players['adp_rank'])
    else:
        # If no ADP data, the score is just the VORP rank
        players['draft_score'] = players['vorp_rank']
        
    return players

def simulate_cpu_pick(available_players: pd.DataFrame, team: Team) -> str:
    """
    Simulates a CPU pick using a balanced approach of Best Player Available (BPA),
    positional need, and positional scarcity.
    """
    # 1. Calculate draft_score for all available players to establish a BPA baseline.
    available_players = calculate_draft_score(available_players)

    # 2. Identify team needs and positional scarcity.
    needs = team.get_positional_needs()
    scarcity = calculate_positional_scarcity(available_players)

    # 3. Apply bonuses to the draft_score to "nudge" the decision.
    if needs:
        needed_player_indices = available_players[available_players['position'].isin(needs)].index
        available_players.loc[needed_player_indices, 'draft_score'] *= 0.85

    if scarcity:
        scarcest_position = max(scarcity, key=scarcity.get)
        top_player_at_scarcest = available_players[available_players['position'] == scarcest_position].sort_values(by='VORP', ascending=False).head(1)
        if not top_player_at_scarcest.empty:
            player_index = top_player_at_scarcest.index[0]
            available_players.loc[player_index, 'draft_score'] -= 10

    # 4. Make the pick based on the adjusted score.
    top_10 = available_players.sort_values(by='draft_score', ascending=True).head(10)
    
    if top_10.empty:
        return "No players available"
        
    choices = top_10['display_name'].tolist()
    
    probabilities = [0.60, 0.20, 0.10, 0.05, 0.02, 0.01, 0.005, 0.005, 0.005, 0.005]
    
    if len(choices) < len(probabilities):
        probabilities = probabilities[:len(choices)]
        prob_sum = sum(probabilities)
        if prob_sum > 0:
            probabilities = [p / prob_sum for p in probabilities]
        else:
            probabilities = [1 / len(choices)] * len(choices)

    return np.random.choice(choices, p=probabilities)
