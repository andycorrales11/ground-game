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
    df_pos = df[df['pos'] == position].copy()
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
    points_col = f"fantasy_points_{draft_sim.format.lower().replace('halfppr', 'half_ppr')}"
    player_points = player_to_eval[points_col]
    player_position = player_to_eval['pos']
    logging.debug(f"VONA Calc: Evaluating {player_to_eval['display_name']} ({player_position}) with {player_points} points.")
    logging.debug(f"VONA Calc: Picks to simulate: {picks_to_simulate}")

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
            logging.debug("VONA Calc: No more players available during simulation.")
            break # No more players to draft

        # Ensure VORP is calculated for the simulation frame
        for position in ['QB', 'RB', 'WR', 'TE']:# Only calculate VORP for skill positions
            available_for_cpu = calculate_vorp(available_for_cpu, position, teams=draft_sim.teams, format=draft_sim.format)

        cpu_pick_name = simulate_cpu_pick(available_for_cpu, cpu_team, full_player_df)
        pos = draft_sim.draft_player(utils.normalize_name(cpu_pick_name))
        if pos:
            cpu_team.add_player(cpu_pick_name, pos)
            logging.debug(f"VONA Calc: Sim pick {pick_num}: CPU (Team {team_index + 1}) drafted {cpu_pick_name} ({pos})")
        else:
            logging.debug(f"VONA Calc: Sim pick {pick_num}: CPU (Team {team_index + 1}) failed to draft a player.")


    # After simulation, find the best available player at the same position
    remaining_players = draft_sim.get_available_players()
    best_remaining_at_pos = remaining_players[remaining_players['pos'] == player_position]
    logging.debug(f"VONA Calc: Best remaining at {player_position}:\n{best_remaining_at_pos.head()}")

    if best_remaining_at_pos.empty:
        logging.debug(f"VONA Calc: No players left at {player_position} after simulation. VONA set to 0.0.")
        # If no players are left at the position, the value is 0 per new requirement
        return 0.0

    next_best_points = best_remaining_at_pos.sort_values(by=points_col, ascending=False).iloc[0][points_col]
    logging.debug(f"VONA Calc: Next best {player_position} points: {next_best_points}")

    vona_value = player_points - next_best_points
    logging.debug(f"VONA Calc: Raw VONA value: {vona_value}")

    # If VONA is NaN or negative, set to 0
    if pd.isna(vona_value) or vona_value < 0:
        logging.debug(f"VONA Calc: VONA is NaN or negative ({vona_value}). Setting to 0.0.")
        return 0.0
    else:
        return vona_value


def create_vbd_big_board(season: int = 2024, format: str = config.DEFAULT_DRAFT_FORMAT, teams: int = config.DEFAULT_TEAMS) -> pd.DataFrame:
    """
    Creates a VORP-based "big board" for all positions, incorporating ADP data.
    Kickers and Defenses will be included but will have a VORP of 0.
    """
    # 1. Load player data from the database
    base_df = data_service.load_player_data()
    if base_df is None or base_df.empty:
        logging.error("Could not load player data, cannot create big board.")
        return pd.DataFrame()

    # Ensure base columns exist
    if 'normalized_name' not in base_df.columns and 'display_name' in base_df.columns:
        base_df['normalized_name'] = base_df['display_name'].apply(utils.normalize_name)

    # Map format to database column names
    adp_col_map = {'STD': 'std_adp', 'PPR': 'ppr_adp', 'HalfPPR': 'half_ppr_adp'}
    proj_col_map = {'STD': 'std_proj_pts', 'PPR': 'ppr_proj_pts', 'HalfPPR': 'half_ppr_proj_pts'}

    adp_column = adp_col_map.get(format)
    proj_column = proj_col_map.get(format)

    # Rename the format-specific ADP column to a generic 'ADP'
    if adp_column and adp_column in base_df.columns:
        base_df.rename(columns={adp_column: 'ADP'}, inplace=True)
    else:
        logging.warning(f"ADP column for format '{format}' not found. ADP values will be missing.")
        base_df['ADP'] = None

    # Rename the format-specific projection column to the generic 'fantasy_points' name expected by VORP calculation
    fantasy_points_col = f"fantasy_points_{format.lower().replace('halfppr', 'half_ppr')}"
    if proj_column and proj_column in base_df.columns:
        base_df.rename(columns={proj_column: fantasy_points_col}, inplace=True)
    else:
        logging.warning(f"Projection column for format '{format}' not found. Fantasy points will be missing.")
        base_df[fantasy_points_col] = 0.0

    # 4. Calculate VORP for all positions
    all_positions = base_df['pos'].unique()
    final_df = base_df.copy()
    for position in all_positions:
        if position in ['QB', 'RB', 'WR', 'TE']: # Only calculate VORP for skill positions
            final_df = calculate_vorp(final_df, position, teams, format)

    # Sort the final big board by VORP
    final_df.sort_values(by='VORP', ascending=False, inplace=True)
    
    return final_df