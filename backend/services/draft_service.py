import pandas as pd
import numpy as np
from .draft import Draft, Team
from backend import config
from .vbd_service import calculate_vorp


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
        players['draft_score'] = (0.3 * players['vorp_rank']) + (0.7 * players['adp_rank'])
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
    # This is now done on a copy to avoid SettingWithCopyWarning.
    available_players = calculate_draft_score(available_players)

    # 2. Identify team needs and positional scarcity.
    needs = team.get_positional_needs()
    scarcity = calculate_positional_scarcity(available_players)

    # 3. Apply bonuses to the draft_score to "nudge" the decision.
    # A lower score is better.

    # Need-based bonus: Give a small boost to players in needed positions.
    if needs:
        # Improve the draft score by 15% for players in a needed position.
        needed_player_indices = available_players[available_players['position'].isin(needs)].index
        available_players.loc[needed_player_indices, 'draft_score'] *= 0.85

    # Scarcity-based bonus: Give a small boost to the top player at the scarcest position.
    if scarcity:
        scarcest_position = max(scarcity, key=scarcity.get)
        # Find the top player at the scarcest position
        top_player_at_scarcest = available_players[available_players['position'] == scarcest_position].sort_values(by='VORP', ascending=False).head(1)
        if not top_player_at_scarcest.empty:
            player_index = top_player_at_scarcest.index[0]
            # Apply a modest bonus, equivalent to improving their rank by ~5-10 spots.
            available_players.loc[player_index, 'draft_score'] -= 10

    # 4. Make the pick based on the adjusted score.
    # More heavily weight the top players to make smarter, more realistic picks.
    top_10 = available_players.sort_values(by='draft_score', ascending=True).head(10)
    
    if top_10.empty:
        if not available_players.empty:
            top_10 = available_players.sort_values(by='draft_score', ascending=True).head(10)
        else:
            return "No players available" # Should not happen if draft stops correctly
        
    choices = top_10['display_name'].tolist()
    
    # Probabilities favor the top-ranked players more heavily.
    probabilities = [0.40, 0.25, 0.15, 0.10, 0.05, 0.02, 0.01, 0.01, 0.005, 0.005]
    
    # Adjust probabilities if fewer than 10 players are available
    if len(choices) < len(probabilities):
        probabilities = probabilities[:len(choices)]
        # Normalize probabilities so they sum to 1
        prob_sum = sum(probabilities)
        if prob_sum > 0:
            probabilities = [p / prob_sum for p in probabilities]
        else: # If all probabilities are zero, make them uniform
            probabilities = [1 / len(choices)] * len(choices)

    return np.random.choice(choices, p=probabilities)



def calculate_vona(player_to_eval: pd.Series, draft_sim: Draft, teams_list_sim: list[Team], picks_to_simulate: int, teams: int, current_pick: int, draft_order: str) -> float:
    """
    Calculates a more accurate VONA by simulating the draft picks until the user's next turn.
    """
    # Get the points and position of the player being evaluated
    points_col = f"fantasy_points{'' if draft_sim.format == 'STD' else '_' + draft_sim.format.lower()}"
    player_points = player_to_eval[points_col]
    player_position = player_to_eval['position']

    # Simulate the picks
    for i in range(picks_to_simulate):
        pick_num = current_pick + i + 1
        current_round = (pick_num - 1) // teams + 1

        if draft_order == 'snake' and current_round % 2 == 0:
            team_index = teams - ((pick_num - 1) % teams) - 1
        else:
            team_index = (pick_num - 1) % teams
        
        cpu_team = teams_list_sim[team_index]
        
        # Simulate the pick for the CPU team
        available_for_cpu = draft_sim.get_available_players()
        if available_for_cpu.empty:
            break # No more players to draft

        # Ensure VORP is calculated for the simulation frame
        for position in ['QB', 'RB', 'WR', 'TE']:
            available_for_cpu = calculate_vorp(available_for_cpu, position, teams=draft_sim.teams, format=draft_sim.format)

        cpu_pick_name = simulate_cpu_pick(available_for_cpu, cpu_team)
        pos = draft_sim.draft_player(cpu_pick_name)
        if pos:
            cpu_team.add_player(cpu_pick_name, pos)

    # After simulation, find the best available player at the same position
    remaining_players = draft_sim.get_available_players()
    best_remaining_at_pos = remaining_players[remaining_players['position'] == player_position]
    
    if best_remaining_at_pos.empty:
        # If no players are left at the position, the value is the player's own score
        return player_points
    
    next_best_points = best_remaining_at_pos.sort_values(by=points_col, ascending=False).iloc[0][points_col]
    
    return player_points - next_best_points


