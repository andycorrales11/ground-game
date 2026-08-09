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
    if format not in utils.SCORING_FORMATS:
        raise ValueError(f"Unsupported format: {format}")

    points_column = utils.points_column(format)
    if points_column not in df.columns:
        raise KeyError(f"Points column '{points_column}' not found in DataFrame.")

    # Ensure VORP column exists. It starts as NaN, not 0.0: 0 means "exactly
    # replacement level", which is a real and fairly good player, so using it for
    # "no value computed" floats every unknown above everyone below replacement.
    if 'VORP' not in df.columns:
        df['VORP'] = float('nan')

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

    # Find the replacement player. Players with no projection are excluded from the
    # ranking first -- a NaN landing on the replacement index would otherwise make
    # every VORP at the position NaN.
    ranked = df_pos[df_pos[points_column].notna()]
    if len(ranked) > replacement_level:
        replacement_value = ranked.iloc[replacement_level][points_column]
    else:
        replacement_value = 0 # No replacement player found, so VORP is just their score

    # Calculate VORP for the position, applying the positional adjustment. A player
    # with no projection keeps NaN: they are unranked, not replacement level.
    # _json_safe_records turns it into null at the edge, every sort here uses the
    # default na_position='last', and the CPU ranks with na_option='bottom'.
    adjustment_factor = config.POSITION_ADJUSTMENT.get(position, 1.0)
    df_pos['VORP_pos'] = (df_pos[points_column] - replacement_value) * adjustment_factor

    # Update the main DataFrame's VORP column for the specific position
    df.loc[df_pos.index, 'VORP'] = df_pos['VORP_pos']
    
    return df


# How many forward simulations to average when estimating what survives to the
# user's next turn. CPU picks are randomized, so a single run is noisy; each extra
# run costs one more pass of picks_to_simulate CPU picks.
VONA_SIMULATION_RUNS = 5


def simulate_to_next_turn(
    draft_obj: Draft,
    teams_list: list[Team],
    picks_to_simulate: int,
    current_pick: int,
) -> pd.DataFrame:
    """
    Plays out the CPU picks between now and the user's next turn.

    Returns the pool that survives. The caller's Draft and Teams are left untouched.
    """
    draft_sim = Draft(
        draft_obj.players.copy(), draft_obj.format, draft_obj.teams,
        draft_obj.rounds, draft_obj.roster, draft_obj.order,
    )
    draft_sim.drafted_players = draft_obj.drafted_players.copy()
    # Team.copy() carries the picks already made. Building these with
    # Team(roster=t.roster.copy()) only copied the slot *names*, so the simulated
    # opponents started every run with empty rosters and drafted as if it were
    # round one.
    teams_sim = [t.copy() for t in teams_list]

    teams = draft_obj.teams
    draft_order = draft_obj.order

    for i in range(picks_to_simulate):
        pick_num = current_pick + i + 1
        current_round = (pick_num - 1) // teams + 1

        if draft_order == 'snake' and current_round % 2 == 0:
            team_index = teams - ((pick_num - 1) % teams) - 1
        else:
            team_index = (pick_num - 1) % teams

        available_for_cpu = draft_sim.get_available_players()
        if available_for_cpu.empty:
            break

        # Only the skill positions are recomputed against the shrinking pool. K and
        # DEF keep the VORP create_vbd_big_board gave them, which barely moves as
        # the draft runs, and recomputing them here would cost 50% more passes
        # through calculate_vorp in the hottest loop in the app.
        for position in ('QB', 'RB', 'WR', 'TE'):
            available_for_cpu = calculate_vorp(
                available_for_cpu, position, teams=teams, format=draft_sim.format
            )

        cpu_team = teams_sim[team_index]
        cpu_pick_name = utils.normalize_name(simulate_cpu_pick(available_for_cpu, cpu_team))
        pos = draft_sim.draft_player(cpu_pick_name)
        if pos:
            cpu_team.add_player(cpu_pick_name, pos)

    return draft_sim.get_available_players()


def calculate_vona_board(
    available_players: pd.DataFrame,
    draft_obj: Draft,
    teams_list: list[Team],
    picks_to_simulate: int,
    current_pick: int,
    runs: int = VONA_SIMULATION_RUNS,
) -> dict[str, float]:
    """
    VONA for every available player, from one shared set of forward simulations.

    VONA asks: how much do I lose by waiting? That is the candidate's projection
    minus the best projection still available at their position on my next turn --
    and the forward simulation that answers the second half never looks at the
    candidate at all.

    This used to be run once per candidate (50 near-identical simulations, ~17s),
    which was both slow and subtly wrong: every candidate was scored against a
    different random future, so the VONA column was not internally comparable.
    Simulating a few times up front and averaging the best survivor per position
    scores the whole board against the same expected outcome.

    Returns {display_name: vona}, clamped at 0 -- a player who is still there next
    turn costs you nothing to wait on.
    """
    points_col = utils.points_column(draft_obj.format)

    if available_players.empty:
        return {}

    # No picks in between means nothing comes off the board, so waiting is free.
    if picks_to_simulate <= 0:
        return {name: 0.0 for name in available_players['display_name']}

    best_by_pos: dict[str, list[float]] = {}
    for _ in range(max(1, runs)):
        survivors = simulate_to_next_turn(
            draft_obj, teams_list, picks_to_simulate, current_pick
        )
        if survivors.empty:
            continue
        for pos, best in survivors.groupby('pos')[points_col].max().items():
            if pd.notna(best):
                best_by_pos.setdefault(pos, []).append(best)

    expected_best = {pos: sum(vals) / len(vals) for pos, vals in best_by_pos.items()}

    vona_results: dict[str, float] = {}
    for name, pos, points in zip(
        available_players['display_name'],
        available_players['pos'],
        available_players[points_col],
    ):
        # A position wiped out entirely, or a player with no projection (K/DEF),
        # scores 0 rather than a meaningless number.
        if pos not in expected_best or pd.isna(points):
            vona_results[name] = 0.0
            continue
        vona = points - expected_best[pos]
        vona_results[name] = float(vona) if vona > 0 else 0.0

    return vona_results


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
    fantasy_points_col = utils.points_column(format)
    if proj_column and proj_column in base_df.columns:
        base_df.rename(columns={proj_column: fantasy_points_col}, inplace=True)
    else:
        logging.warning(f"Projection column for format '{format}' not found. Fantasy points will be missing.")
        base_df[fantasy_points_col] = 0.0

    # 4. Calculate VORP for all positions
    final_df = base_df.copy()
    for position in base_df['pos'].unique():
        if position in config.VORP_POSITIONS:
            final_df = calculate_vorp(final_df, position, teams, format)

    # Sort the final big board by VORP
    final_df.sort_values(by='VORP', ascending=False, inplace=True)
    
    return final_df