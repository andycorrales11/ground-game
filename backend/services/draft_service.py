from time import sleep
import pandas as pd
import argparse
import numpy as np
from .draft import Draft, Team
from backend import config
from .vbd_service import create_vbd_big_board, calculate_vorp

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


def run_draft_simulation(draft: Draft, teams_list: list[Team], user_pick_number: int, user_picks: list[int], rounds: int, teams: int, non_interactive: bool = False):
    """
    Runs the main draft simulation loop.
    """
    total_picks = rounds * teams
    original_big_board = draft.players.copy()

    try:
        for pick_num_idx, pick_num in enumerate(range(1, total_picks + 1)):
            current_round = (pick_num - 1) // teams + 1
            
            if draft.order == 'snake' and current_round % 2 == 0:
                team_index = teams - ((pick_num - 1) % teams) - 1
            else:
                team_index = (pick_num - 1) % teams
            
            current_team = teams_list[team_index]

            print(f"\n{'='*10} Round {current_round}, Pick {pick_num} (Team {team_index + 1}) {'='*10}")

            available_players = draft.get_available_players().copy()
            if available_players.empty:
                print("\nNo more players available. The draft is effectively over.")
                break
            
            # Calculate VORP for all available players
            if not available_players.empty:
                for position in ['QB', 'RB', 'WR', 'TE']:
                    available_players = calculate_vorp(available_players, position, teams=draft.teams, format=draft.format)
                
                available_players.sort_values(by='VORP', ascending=False, inplace=True)
                draft.players = available_players

            if pick_num in user_picks:
                # --- Start of User's Pick Logic ---
                if available_players.empty:
                    print("\nNo more players available. The draft is effectively over.")
                    break

                print("\nCalculating VONA... (this may take a moment)")
                
                # Determine picks to simulate for VONA
                current_user_pick_index = user_picks.index(pick_num)
                if current_user_pick_index + 1 < len(user_picks):
                    next_user_pick = user_picks[current_user_pick_index + 1]
                    picks_to_simulate = next_user_pick - pick_num - 1
                else:
                    picks_to_simulate = 0

                # Ensure VONA column exists before calculation
                if 'VONA' not in available_players.columns:
                    available_players['VONA'] = 0.0

                # Calculate VONA for top players
                if picks_to_simulate > 0:
                    try:
                        vona_values = {}
                        top_players_to_eval = available_players.head(30)
                        
                        for index, player_row in top_players_to_eval.iterrows():
                            draft_sim = Draft(draft.players.copy(), draft.format, draft.teams, draft.rounds, draft.roster, draft.order)
                            draft_sim.drafted_players = draft.drafted_players.copy()
                            teams_list_sim = [Team(roster=t.roster.copy()) for t in teams_list]
                            sim_user_team = teams_list_sim[team_index]
                            
                            sim_pos = draft_sim.draft_player(player_row['display_name'])
                            if sim_pos:
                                sim_user_team.add_player(player_row['display_name'], sim_pos)
                                vona = calculate_vona(player_row, draft_sim, teams_list_sim, picks_to_simulate, teams, pick_num, draft.order)
                                vona_values[player_row.name] = vona
                            else:
                                vona_values[player_row.name] = 0
                        
                        # Map values using the DataFrame index for accuracy
                        vona_series = pd.Series(vona_values)
                        available_players.loc[:, 'VONA'] = vona_series

                    except Exception as e:
                        print(f"\n[Error] Could not calculate VONA due to an error: {e}")
                        print("Defaulting VONA to 0. You can still sort by VORP or ADP.")
                        available_players.loc[:, 'VONA'] = 0.0
                else:
                    available_players.loc[:, 'VONA'] = 0.0
                
                if non_interactive:
                    print("\nYour pick is up! (Auto-picking best player by VONA)")
                    # In non-interactive mode, auto-pick the best player based on VONA
                    best_player_name = available_players.sort_values(by='VONA', ascending=False).iloc[0]['display_name']
                    pos = draft.draft_player(best_player_name)
                    if pos:
                        current_team.add_player(best_player_name, pos)
                        print(f"You drafted: {best_player_name} ({pos})")
                    else:
                        print("[Error] Auto-pick failed.")
                    continue # Skip interactive loop

                sort_col = 'ADP'
                position_filter = 'ALL'

                while True:
                    print("\nYour pick is up!")
                    
                    drafted_info = original_big_board[original_big_board['display_name'].isin(draft.drafted_players)]
                    drafted_counts = drafted_info['position'].value_counts().to_dict()
                    print("Drafted players by position:", drafted_counts)
                    print("Your roster:", {k: v for k, v in current_team.roster.items() if v is not None})

                    # Apply position filter
                    filtered_board = available_players.copy()
                    if position_filter != 'ALL':
                        if position_filter == 'FLEX':
                            filtered_board = filtered_board[filtered_board['position'].isin(['RB', 'WR', 'TE'])]
                        else:
                            filtered_board = filtered_board[filtered_board['position'] == position_filter]

                    print(f"\nBest available players (Filter: {position_filter}, Sorted by: {sort_col}):")
                    
                    display_cols = ['display_name', 'position', 'VORP', 'VONA']
                    if 'ADP' in filtered_board.columns:
                        display_cols.append('ADP')
                    
                    existing_display_cols = [col for col in display_cols if col in filtered_board.columns]
                    
                    ascending_order = True if sort_col == 'ADP' else False
                    
                    if not filtered_board.empty:
                        print(filtered_board.sort_values(by=sort_col, ascending=ascending_order).head(15)[existing_display_cols])
                    else:
                        print("No players available for the current filter.")

                    command = input("\nEnter command ('draft <name>', 'sort <col>', 'filter <pos>', 'help'): ")
                    
                    if command.lower().startswith('draft '):
                        player_name = command[6:]
                        pos = draft.draft_player(player_name)
                        if pos:
                            current_team.add_player(player_name, pos)
                            print(f"You drafted: {player_name} ({pos})")
                            break
                        else:
                            print("[Error] Invalid name or player already drafted.")
                    elif command.lower().startswith('sort '):
                        new_sort_col = command[5:].upper()
                        if new_sort_col in ['VORP', 'VONA', 'ADP']:
                            if new_sort_col not in available_players.columns:
                                print(f"[Error] {new_sort_col} data not available.")
                            else:
                                sort_col = new_sort_col
                        else:
                            print("[Error] Can only sort by VORP, VONA, or ADP.")
                    elif command.lower().startswith('filter '):
                        new_filter = command[7:].upper()
                        if new_filter in ['ALL', 'QB', 'RB', 'WR', 'TE', 'FLEX']:
                            position_filter = new_filter
                        else:
                            print("[Error] Invalid position. Use ALL, QB, RB, WR, TE, or FLEX.")
                    elif command.lower() == 'help':
                        print("\nCommands:")
                        print("  draft <name>  - Drafts the specified player.")
                        print("  sort <col>    - Sorts by VORP, VONA, or ADP.")
                        print("  filter <pos>  - Filters by position (ALL, QB, RB, WR, TE, FLEX).")
                        print("  help          - Shows this help message.")
                    else:
                        print("[Error] Invalid command.")
            else:
                # CPU's pick
                print(f"CPU (Team {team_index + 1}) is on the clock...")
                sleep(1)
                cpu_pick_name = simulate_cpu_pick(available_players, current_team)
                pos = draft.draft_player(cpu_pick_name)
                if pos:
                    current_team.add_player(cpu_pick_name, pos)
                    print(f"CPU (Team {team_index + 1}) drafted: {cpu_pick_name} ({pos})")
                else:
                    print(f"CPU (Team {team_index + 1}) failed to draft a player.")
            sleep(1)
    except Exception as e:
        print(f"\n[Error] An unexpected error occurred during the draft simulation: {e}")
        print("The draft will now terminate.")
        import traceback
        traceback.print_exc()

    print("\nDraft complete!")
    print("Your final roster:")
    print(teams_list[user_pick_number - 1].roster)


def main():
    parser = argparse.ArgumentParser(description="Fantasy Football Draft Simulator")
    parser.add_argument("pick", type=int, help="Your pick number (1-based)")
    parser.add_argument("--order", choices=["snake", "normal"], default="snake", help="Draft order type")
    parser.add_argument("--teams", type=int, default=config.DEFAULT_TEAMS, help="Number of teams")
    parser.add_argument("--rounds", type=int, default=config.DEFAULT_ROUNDS, help="Number of rounds")
    parser.add_argument("--format", type=str, default=config.DEFAULT_DRAFT_FORMAT, help="Draft format (e.g., STD, PPR)")
    parser.add_argument("--season", type=int, default=2024, help="Season for stats (default: 2024)")
    parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive mode for testing")
    args = parser.parse_args()

    user_picks = get_user_picks(args.pick, args.order, args.teams, args.rounds)
    print("Your picks are at positions:", user_picks)
    
    print("Creating initial big board...")
    big_board = create_vbd_big_board(season=args.season, format=args.format, teams=args.teams)
    
    if big_board.empty:
        print("[Error] Big board could not be created. Exiting.")
        return

    draft = Draft(big_board, args.format, args.teams, args.rounds, order=args.order)
    teams_list = [Team() for _ in range(args.teams)]
    
    run_draft_simulation(draft, teams_list, args.pick, user_picks, args.rounds, args.teams, non_interactive=args.non_interactive)


if __name__ == "__main__":
    main()