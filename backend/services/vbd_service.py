import pandas as pd
from backend import config
from backend.services import data_service
import logging

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

    points_column = f"fantasy_points{ '' if format == 'STD' else '_' + format.lower()}"
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


def create_vbd_big_board(season: int = 2024, format: str = config.DEFAULT_DRAFT_FORMAT, teams: int = config.DEFAULT_TEAMS) -> pd.DataFrame:
    """
    Creates a VORP-based "big board" for all positions, incorporating ADP data.

    Returns:
        A DataFrame of all players, sorted by VORP.
    """
    all_players_df = pd.DataFrame()

    # Load ADP data
    adp_df = data_service.load_adp_data()
    if adp_df is None:
        adp_df = pd.DataFrame() # Ensure adp_df is a DataFrame

    for position in ['QB', 'RB', 'WR', 'TE']:
        pos_df = data_service.load_stats_data(position, season)
        if pos_df is not None:
            # Calculate VORP and VONA
            pos_vorp_df = calculate_vorp(pos_df, position, teams, format)
            
            all_players_df = pd.concat([all_players_df, pos_vorp_df], ignore_index=True)
        else:
            logging.warning(f"Stats file not found for {position}s in season {season}. Skipping.")
            continue

    # Merge ADP data
    if not adp_df.empty:
        adp_column_name = f"ADP_{format.upper()}"
        if adp_column_name in adp_df.columns:
            all_players_df = pd.merge(all_players_df, adp_df[['display_name', adp_column_name]], on='display_name', how='left')
            all_players_df.rename(columns={adp_column_name: 'ADP'}, inplace=True)
        else:
            logging.warning(f"ADP column '{adp_column_name}' not found in ADP data. Skipping ADP merge.")

    # Sort the final big board by VORP
    all_players_df.sort_values(by='VORP', ascending=False, inplace=True)
    
    return all_players_df