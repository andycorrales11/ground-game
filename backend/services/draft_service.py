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

def simulate_cpu_pick(available_players: pd.DataFrame, team: Team) -> str:
    """
    Simulates a CPU pick based on ADP and positional needs.
    """
    # If ADP data is not available, fall back to VORP
    if 'ADP' not in available_players.columns:
        return simulate_cpu_pick_vorp(available_players, team)

    needs = team.get_positional_needs()
    
    # Prioritize positional needs
    if needs:
        needy_players = available_players[available_players['position'].isin(needs)]
        if not needy_players.empty:
            available_players = needy_players

    # Handle missing ADP values by filling them with a high number
    available_players['ADP'] = available_players['ADP'].fillna(999)

    top_6 = available_players.sort_values(by='ADP', ascending=True).head(6)
    if len(top_6) == 0:
        # If no players are left, try to pick from the general pool
        top_6 = available_players.sort_values(by='ADP', ascending=True).head(6)
        if len(top_6) == 0:
            return "No players available"
        
    choices = top_6['display_name'].tolist()
    
    # Probabilities for top 6 players (higher probability for better ADP)
    probabilities = [0.35, 0.25, 0.15, 0.10, 0.10, 0.05]
    
    # Adjust probabilities if fewer than 6 players are available
    if len(choices) < len(probabilities):
        probabilities = probabilities[:len(choices)]
        # Normalize probabilities
        probabilities = [p / sum(probabilities) for p in probabilities]

    return np.random.choice(choices, p=probabilities)

def simulate_cpu_pick_vorp(available_players: pd.DataFrame, team: Team) -> str:
    """
    Fallback CPU pick simulation using VORP.
    """
    needs = team.get_positional_needs()
    
    if needs:
        needy_players = available_players[available_players['position'].isin(needs)]
        if not needy_players.empty:
            available_players = needy_players

    top_6 = available_players.sort_values(by='VORP', ascending=False).head(6)
    if len(top_6) == 0:
        top_6 = available_players.sort_values(by='VORP', ascending=False).head(6)
        if len(top_6) == 0:
            return "No players available"
        
    choices = top_6['display_name'].tolist()
    probabilities = [0.35, 0.25, 0.15, 0.10, 0.10, 0.05]
    
    if len(choices) < len(probabilities):
        probabilities = probabilities[:len(choices)]
        probabilities = [p / sum(probabilities) for p in probabilities]

    return np.random.choice(choices, p=probabilities)

def calculate_true_vona(player_to_eval: pd.Series, draft_sim: Draft, teams_list_sim: list[Team], picks_to_simulate: int, teams: int, current_pick: int, draft_order: str) -> float:
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


def run_draft_simulation(draft: Draft, teams_list: list[Team], user_pick_number: int, user_picks: list[int], rounds: int, teams: int):
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

                print("\nCalculating TRUEVONA... (this may take a moment)")
                
                # Determine picks to simulate for VONA
                current_user_pick_index = user_picks.index(pick_num)
                if current_user_pick_index + 1 < len(user_picks):
                    next_user_pick = user_picks[current_user_pick_index + 1]
                    picks_to_simulate = next_user_pick - pick_num - 1
                else:
                    picks_to_simulate = 0

                # Ensure TRUEVONA column exists before calculation
                if 'TRUEVONA' not in available_players.columns:
                    available_players['TRUEVONA'] = 0.0

                # Calculate TRUEVONA for top players
                if picks_to_simulate > 0:
                    try:
                        true_vona_values = {}
                        top_players_to_eval = available_players.head(30)
                        
                        for index, player_row in top_players_to_eval.iterrows():
                            draft_sim = Draft(draft.players.copy(), draft.format, draft.teams, draft.rounds, draft.roster, draft.order)
                            draft_sim.drafted_players = draft.drafted_players.copy()
                            teams_list_sim = [Team(roster=t.roster.copy()) for t in teams_list]
                            sim_user_team = teams_list_sim[team_index]
                            
                            sim_pos = draft_sim.draft_player(player_row['display_name'])
                            if sim_pos:
                                sim_user_team.add_player(player_row['display_name'], sim_pos)
                                vona = calculate_true_vona(player_row, draft_sim, teams_list_sim, picks_to_simulate, teams, pick_num, draft.order)
                                true_vona_values[player_row.name] = vona
                            else:
                                true_vona_values[player_row.name] = 0
                        
                        # Map values using the DataFrame index for accuracy
                        available_players['TRUEVONA'] = available_players.index.map(true_vona_values).fillna(0)

                    except Exception as e:
                        print(f"\n[Error] Could not calculate TRUEVONA due to an error: {e}")
                        print("Defaulting TRUEVONA to 0. You can still sort by VORP or ADP.")
                        available_players['TRUEVONA'] = 0.0
                else:
                    available_players['TRUEVONA'] = 0.0
                
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
                    
                    display_cols = ['display_name', 'position', 'VORP', 'TRUEVONA']
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
                        if new_sort_col in ['VORP', 'TRUEVONA', 'ADP']:
                            if new_sort_col not in available_players.columns:
                                print(f"[Error] {new_sort_col} data not available.")
                            else:
                                sort_col = new_sort_col
                        else:
                            print("[Error] Can only sort by VORP, TRUEVONA, or ADP.")
                    elif command.lower().startswith('filter '):
                        new_filter = command[7:].upper()
                        if new_filter in ['ALL', 'QB', 'RB', 'WR', 'TE', 'FLEX']:
                            position_filter = new_filter
                        else:
                            print("[Error] Invalid position. Use ALL, QB, RB, WR, TE, or FLEX.")
                    elif command.lower() == 'help':
                        print("\nCommands:")
                        print("  draft <name>  - Drafts the specified player.")
                        print("  sort <col>    - Sorts by VORP, TRUEVONA, or ADP.")
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
    
    run_draft_simulation(draft, teams_list, args.pick, user_picks, args.rounds, args.teams)


if __name__ == "__main__":
    main()
