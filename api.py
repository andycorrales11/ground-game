# This file will contain the interactive CLI for the draft simulation.

import argparse
import logging
import pandas as pd
from time import sleep
from backend.services.draft import Draft, Team
from backend import config
from backend.services.vbd_service import create_vbd_big_board, calculate_vorp, calculate_vona
from backend.services.draft_service import get_user_picks
from backend.services.simulation_service import simulate_cpu_pick, simulate_user_auto_pick
from backend.services import sleeper_service, data_service
from backend import utils

def run_draft(
    draft: Draft,
    teams_list: list[Team],
    user_pick_slot: int,
    user_picks_simulation: list[int],
    draft_id: str | None = None,
    non_interactive: bool = False
):
    """
    Runs the main draft loop for either a live assistant or a simulation.
    This function is the single source of truth for draft logic.
    """
    original_big_board = draft.players.copy()
    
    # --- Pre-calculate draft order for live mode ---
    picks_order = []
    slot_to_roster_id = {}
    if draft_id:
        settings = sleeper_service.get_draft_settings(draft_id)
        slot_to_roster_id = settings.get('slot_to_roster_id', {})
        user_roster_id = slot_to_roster_id.get(str(user_pick_slot))
        if not user_roster_id:
            print(f"Error: Could not find your roster ID for pick slot {user_pick_slot}.")
            return
        
        for r in range(1, draft.rounds + 1):
            round_order = list(range(1, draft.teams + 1))
            if draft.order == 'snake' and r % 2 == 0:
                round_order.reverse()
            picks_order.extend(round_order)

    # --- Main Draft Loop ---
    current_pick_num = 0
    while current_pick_num < (draft.rounds * draft.teams):
        
        is_user_turn = False
        team_index = -1

        # --- Determine whose turn it is ---
        if draft_id:
            # LIVE MODE: Poll API and check state
            print("\nWaiting for the next pick...")
            while True:
                all_picks = sleeper_service.get_all_picks(draft_id)
                picks_made = len(all_picks)

                # Process any new picks that have appeared since last check
                if picks_made > current_pick_num:
                    for i in range(current_pick_num, picks_made):
                        pick = all_picks[i]
                        player_id = pick.get('player_id')
                        roster_id = pick.get('roster_id') or slot_to_roster_id.get(str(pick.get('draft_slot')))
                        
                        if not player_id or not roster_id: continue

                        player_info = original_big_board[original_big_board['sleeper_id'] == player_id].iloc[0]
                        draft.draft_player(player_info['display_name'])
                        
                        print(f"Pick {i + 1}: Team {roster_id} drafted {player_info['display_name']} ({player_info['position']})")
                    current_pick_num = picks_made

                # Now, determine who is on the clock for the *next* pick
                if current_pick_num >= len(picks_order):
                    print("Draft appears to be complete.")
                    break

                next_pick_slot = picks_order[current_pick_num]
                on_clock_roster_id = slot_to_roster_id.get(str(next_pick_slot))

                if on_clock_roster_id == user_roster_id:
                    is_user_turn = True
                    team_index = int(on_clock_roster_id) - 1
                    break # Exit waiting loop and proceed to user turn logic
                else:
                    print(f"Team {on_clock_roster_id} is on the clock. Checking again in 10 seconds...")
                    sleep(10)
        
        else:
            # SIMULATION MODE: Determine whose turn it is
            current_pick_num += 1
            current_round = (current_pick_num - 1) // draft.teams + 1
            
            if draft.order == 'snake' and current_round % 2 == 0:
                team_index = draft.teams - ((current_pick_num - 1) % draft.teams) - 1
            else:
                team_index = (current_pick_num - 1) % draft.teams
            
            is_user_turn = current_pick_num in user_picks_simulation

        # --- USER'S TURN LOGIC (used by both modes) ---
        if is_user_turn:
            current_team = teams_list[team_index]
            available_players = draft.get_available_players().copy()
            if available_players.empty:
                print("No more players available.")
                break

            # VONA Calculation
            print("Calculating VONA... (this may take a moment)")
            
            next_user_pick_index = -1
            if draft_id:
                # Live mode: find the next pick belonging to the user
                for i in range(current_pick_num, len(picks_order)):
                    if slot_to_roster_id.get(str(picks_order[i])) == user_roster_id:
                        # Find the next one that isn't the current pick
                        if i > current_pick_num:
                            next_user_pick_index = i
                            break
            else: # Simulation mode
                 current_user_pick_index = user_picks_simulation.index(current_pick_num)
                 if current_user_pick_index + 1 < len(user_picks_simulation):
                     # In sim mode, the pick number is 1-based, index is 0-based
                     next_user_pick_index = user_picks_simulation[current_user_pick_index + 1] - 1

            picks_to_simulate = (next_user_pick_index - current_pick_num) if next_user_pick_index != -1 else 0
            
            if 'VONA' not in available_players.columns: available_players['VONA'] = 0.0

            if picks_to_simulate > 0:
                print(f"Simulating {picks_to_simulate} picks until your next turn...")
                vona_values = {}
                for index, player_row in available_players.head(30).iterrows():
                    # Create a deep copy of the draft state for a clean simulation
                    draft_sim = Draft(draft.players.copy(), draft.format, draft.teams, draft.rounds, draft.roster, draft.order)
                    draft_sim.drafted_players = draft.drafted_players.copy()
                    teams_list_sim = [Team(roster=t.roster.copy()) for t in teams_list]
                    
                    vona = calculate_vona(player_row, draft_sim, teams_list_sim, picks_to_simulate, draft.teams, current_pick_num, draft.order, original_big_board)
                    vona_values[player_row.name] = vona
                available_players.loc[:, 'VONA'] = pd.Series(vona_values)

            if non_interactive and not draft_id: # Auto-pick for simulation only
                player_name = simulate_user_auto_pick(available_players, current_team, original_big_board)
                print(f"Auto-drafting: {player_name}")
            else:
                # Interactive sub-loop
                sort_col, position_filter = 'VONA', 'ALL'
                while True:
                    if position_filter in ['K', 'DEF']: sort_col = 'ADP'
                    print(f"\n--- Your Pick! (Filter: {position_filter}, Sorted by: {sort_col}) ---")
                    
                    filtered_board = available_players.copy()
                    if position_filter != 'ALL':
                        if position_filter == 'FLEX': filtered_board = filtered_board[filtered_board['position'].isin(['RB', 'WR', 'TE'])]
                        else: filtered_board = filtered_board[filtered_board['position'] == position_filter]

                    display_cols = ['display_name', 'position', 'VORP', 'VONA', 'ADP']
                    existing_cols = [c for c in display_cols if c in filtered_board.columns]
                    ascending = sort_col == 'ADP'
                    print(filtered_board.sort_values(by=sort_col, ascending=ascending).head(20)[existing_cols])
                    
                    cmd = input("\nEnter 'draft <name>', 'sort <col>', 'filter <pos>', 'help': ").lower()
                    if cmd.startswith('draft '):
                        player_name = cmd[6:]
                        break
                    elif cmd.startswith('sort '): sort_col = cmd[5:].upper()
                    elif cmd.startswith('filter '): position_filter = cmd[7:].upper()
                    elif cmd == 'help':
                        print("\nCommands: draft, sort, filter, help")
                    else: print("Invalid command.")
            
            # Draft the chosen player
            pos = draft.draft_player(player_name)
            if pos:
                current_team.add_player(player_name, pos)
                print(f"You drafted: {player_name} ({pos})")
                if draft_id:
                    print("Waiting for pick to appear on Sleeper board...")
            else:
                print(f"[Error] Could not draft '{player_name}'. Please try again.")
                if not draft_id: current_pick_num -=1 # Decrement to retry the pick in sim mode

        # --- CPU's TURN LOGIC (simulation mode only) ---
        elif not draft_id:
            current_team = teams_list[team_index]
            available_players = draft.get_available_players()
            print(f"CPU (Team {team_index + 1}) is on the clock...")
            cpu_pick_name = simulate_cpu_pick(available_players, current_team, original_big_board)
            pos = draft.draft_player(cpu_pick_name)
            if pos:
                current_team.add_player(cpu_pick_name, pos)
                print(f"CPU (Team {team_index + 1}) drafted: {cpu_pick_name} ({pos})")
            else:
                print(f"CPU (Team {team_index + 1}) failed to draft a player.")

    # --- Post-Draft Summary ---
    print("\n--- Draft Complete! ---")
    # ... (rest of summary logic can be added here)


def main():
    parser = argparse.ArgumentParser(description="Fantasy Football Draft Tool")
    parser.add_argument("pick", type=int, help="Your pick slot (1-based)")
    parser.add_argument("--draft-id", type=str, help="Sleeper draft ID for live draft assistant mode")
    parser.add_argument("--non-interactive", action="store_true", help="Enable auto-picking for simulation mode")
    # Simulation-specific args
    parser.add_argument("--teams", type=int, help="Number of teams (for simulation)")
    parser.add_argument("--rounds", type=int, help="Number of rounds (for simulation)")
    parser.add_argument("--format", type=str, help="Scoring format (for simulation)")
    parser.add_argument("--order", choices=["snake", "normal"], help="Draft order (for simulation)")
    args = parser.parse_args()

    # --- Mode Selection ---
    if args.draft_id:
        # Live Assistant Mode
        print("--- Live Draft Assistant Mode ---")
        settings = sleeper_service.get_draft_settings(args.draft_id)
        if not settings:
            print("Could not fetch live draft settings. Exiting.")
            return
        
        draft_teams = settings['teams']
        draft_rounds = settings['rounds']
        draft_format = settings['format']
        draft_order = settings['order']
        user_picks = [] # Not used in live mode
    else:
        # Simulation Mode
        print("--- Draft Simulation Mode ---")
        draft_teams = args.teams or config.DEFAULT_TEAMS
        draft_rounds = args.rounds or config.DEFAULT_ROUNDS
        draft_format = (args.format or config.DEFAULT_DRAFT_FORMAT).upper()
        draft_order = args.order or 'snake'
        user_picks = get_user_picks(args.pick, draft_order, draft_teams, draft_rounds)
        print("Your simulated picks are at positions:", user_picks)

    # --- Common Setup ---
    print("Creating big board...")
    big_board = create_vbd_big_board(format=draft_format, teams=draft_teams)
    if big_board.empty:
        print("[Error] Big board could not be created. Exiting.")
        return

    # Add sleeper_id to the big board if it's not there, crucial for live mode
    if 'sleeper_id' not in big_board.columns:
        player_data = data_service.load_adp_data()[['normalized_name', 'sleeper_id']]
        big_board = pd.merge(big_board, player_data, on='normalized_name', how='left')

    draft = Draft(big_board, draft_format, draft_teams, draft_rounds, order=draft_order)
    teams_list = [Team() for _ in range(draft_teams)]

    # --- Run the unified draft function ---
    run_draft(draft, teams_list, args.pick, user_picks, args.draft_id, args.non_interactive)


if __name__ == "__main__":
    main()