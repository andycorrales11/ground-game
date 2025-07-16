import pandas as pd
from backend import config
from backend.services import data_service
from backend import utils
import logging
from .draft import Draft, Team
from .simulation_service import simulate_cpu_pick

# Setup logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

def calculate_vorp(
    df: pd.DataFrame, 
    position: str, 
    teams: int = config.DEFAULT_TEAMS, 
    format: str = config.DEFAULT_DRAFT_FORMAT,
    roster_config = config.DEFAULT_ROSTER_POS
) -> pd.DataFrame:
    """
    Calculates Value Over Replacement Player (VORP) for a given position and merges it back.

    Args:
        df: DataFrame containing player stats for ALL positions.
        position: The position to calculate VORP for (e.g., 'QB', 'RB').
        teams: The number of teams in the league.
        format: The scoring format (e.g., 'STD', 'PPR').
        roster_config: A list representing the league's roster construction.

    Returns:
        The original DataFrame with a 'VORP' column updated for the specified position.
    """
    if format not in ['STD', 'PPR', 'HalfPPR']:
        raise ValueError(f"Unsupported format: {format}")

    points_column = f"fantasy_points_{format.lower()}"
    if points_column not in df.columns:
        raise KeyError(f"Points column '{points_column}' not found in DataFrame.")

    # Ensure VORP column exists
    if 'VORP' not in df.columns:
        df['VORP'] = 0.0

    # Determine replacement level based on roster settings
    num_starters = roster_config.count(position)
    num_flex = roster_config.count('FLEX')

    # A simple approach to FLEX: assume a 50/50 split between RB and WR
    if position == 'RB' or position == 'WR':
        replacement_level = (num_starters * teams) + int(num_flex * teams * 0.5)
    else:
        replacement_level = num_starters * teams

    # Sort players by fantasy points for the specified position
    df_pos = df[df['position'] == position].copy()
    df_pos.sort_values(by=points_column, ascending=False, inplace=True)

    # Find the replacement player
    if len(df_pos) > replacement_level:
        replacement_player = df_pos.iloc[replacement_level]
        replacement_value = replacement_player[points_column]
    else:
        replacement_value = 0 # No replacement player found, so VORP is just their score

    # Calculate VORP for the position, applying the positional adjustment
    adjustment_factor = config.POSITION_ADJUSTMENT.get(position, 1.0)
    df_pos['VORP_pos'] = (df_pos[points_column] - replacement_value) * adjustment_factor
    
    # Update the main DataFrame's VORP column for the specific position
    df.loc[df_pos.index, 'VORP'] = df_pos['VORP_pos']
    
    return df


def calculate_vona(player_to_eval: pd.Series, draft_sim: Draft, teams_list_sim: list[Team], picks_to_simulate: int, teams: int, current_pick: int, draft_order: str, full_player_df: pd.DataFrame) -> float:
    """
    Calculates a more accurate VONA by simulating the draft picks until the user's next turn.
    If the calculated VONA is NaN or negative, it returns 0.
    """
    # Get the points and position of the player being evaluated
    points_col = f"fantasy_points_{draft_sim.format.lower()}"
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

        cpu_pick_name = simulate_cpu_pick(available_for_cpu, cpu_team, full_player_df)
        pos = draft_sim.draft_player(cpu_pick_name)
        if pos:
            cpu_team.add_player(cpu_pick_name, pos)

    # After simulation, find the best available player at the same position
    remaining_players = draft_sim.get_available_players()
    best_remaining_at_pos = remaining_players[remaining_players['position'] == player_position]

    if best_remaining_at_pos.empty:
        # If no players are left at the position, the value is 0 per new requirement
        return 0.0

    next_best_points = best_remaining_at_pos.sort_values(by=points_col, ascending=False).iloc[0][points_col]

    vona_value = player_points - next_best_points

    # If VONA is NaN or negative, set to 0
    if pd.isna(vona_value) or vona_value < 0:
        return 0.0
    else:
        return vona_value


def create_vbd_big_board(season: int = 2024, format: str = config.DEFAULT_DRAFT_FORMAT, teams: int = config.DEFAULT_TEAMS) -> pd.DataFrame:
    """
    Creates a VORP-based "big board" for all positions, incorporating ADP data.
    Kickers and Defenses will be included but will have a VORP of 0.
    """
    # 1. Load ADP data as the base DataFrame to include all players (including K, DEF)
    base_df = data_service.load_adp_data()
    if base_df is None or base_df.empty:
        logging.error("Could not load ADP data, cannot create big board.")
        return pd.DataFrame()

    # Ensure base columns exist
    if 'normalized_name' not in base_df.columns and 'display_name' in base_df.columns:
        base_df['normalized_name'] = base_df['display_name'].apply(utils.normalize_name)
    
    # Rename the format-specific ADP column to a generic 'ADP' for easier use
    adp_column_name = f"ADP_{format}"
    if adp_column_name in base_df.columns:
        base_df.rename(columns={adp_column_name: 'ADP'}, inplace=True)
    else:
        logging.warning(f"ADP column '{adp_column_name}' not found. ADP values will be missing.")
        base_df['ADP'] = None

    # 2. Create a DataFrame for skill positions with fantasy points
    skill_players_df = pd.DataFrame()
    for position in ['QB', 'RB', 'WR', 'TE']:
        pos_df = data_service.load_athletic_projections(position, format)
        if pos_df is not None:
            pos_df.rename(columns={'Player': 'display_name', 'FPS': f'fantasy_points_{format.lower()}'}, inplace=True)
            pos_df['position'] = position
            pos_df['normalized_name'] = pos_df['display_name'].apply(utils.normalize_name)
            skill_players_df = pd.concat([skill_players_df, pos_df], ignore_index=True)
        else:
            logging.warning(f"Athletic projections file not found for {position}. Skipping.")

    # 3. Merge the fantasy points into the base DataFrame
    if not skill_players_df.empty:
        # Select only the key columns to merge from skill_players_df
        points_col = f'fantasy_points_{format.lower()}'
        merge_cols = ['normalized_name', points_col]
        if points_col in skill_players_df.columns:
            base_df = pd.merge(base_df, skill_players_df[merge_cols], on='normalized_name', how='left')
        else:
            base_df[points_col] = 0.0
    else:
        base_df[f'fantasy_points_{format.lower()}'] = 0.0

    # 4. Calculate VORP for all positions (will handle K/DEF gracefully)
    all_positions = base_df['position'].unique()
    final_df = base_df.copy()
    for position in all_positions:
        final_df = calculate_vorp(final_df, position, teams, format)

    # Sort the final big board by VORP
    final_df.sort_values(by='VORP', ascending=False, inplace=True)
    
    return final_df