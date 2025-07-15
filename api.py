
# This file will contain the interactive CLI for the draft simulation.

import argparse
from time import sleep
import pandas as pd
from backend.services.draft import Draft, Team
from backend import config
from backend.services.vbd_service import create_vbd_big_board, calculate_vorp
from backend.services.draft_service import get_user_picks, calculate_vona, simulate_cpu_pick

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
                        if sort_col not in filtered_board.columns:
                            sort_col = 'VORP'
                            ascending_order = False
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
