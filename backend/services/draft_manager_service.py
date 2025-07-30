import pandas as pd
from typing import List, Dict, Any
import uuid
import logging

from backend.services.draft import Draft, Team
from backend import config
from backend.services.vbd_service import create_vbd_big_board, calculate_vona
from backend.services.draft_service import get_user_picks
from backend.services.simulation_service import simulate_cpu_pick, simulate_user_auto_pick
from backend.services import sleeper_service, data_service
from backend.utils import normalize_name

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DraftManagerService:
    _active_draft_sessions: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _calculate_and_store_vona(cls, session_state: Dict[str, Any]):
        draft_obj: Draft = session_state["draft_obj"]
        teams_list: List[Team] = session_state["teams_list"]
        current_pick_num = session_state["current_pick_num"]
        original_big_board = session_state["original_big_board"]
        user_picks_simulation = session_state["user_picks_simulation"]
        draft_id = session_state["draft_id"]
        user_pick_slot = session_state["user_pick_slot"]
        picks_order = session_state["picks_order"]
        slot_to_roster_id = session_state["slot_to_roster_id"]

        vona_results = {}
        available_players = draft_obj.get_available_players().copy()

        if available_players.empty:
            session_state["vona_data"] = vona_results
            return

        # Determine picks to simulate for VONA
        picks_to_simulate = 0
        next_user_pick_num = None # Initialize to None
        current_user_pick_index = -1 # Initialize to -1

        if draft_id:
            # Live mode: find the next pick belonging to the user
            user_roster_id = session_state.get("user_roster_id")
            if user_roster_id:
                next_user_pick_index = -1
                for i in range(current_pick_num, len(picks_order)):
                    if slot_to_roster_id.get(str(picks_order[i])) == user_roster_id:
                        if i > current_pick_num: # Find the next one that isn't the current pick
                            next_user_pick_index = i
                            break
                if next_user_pick_index != -1: # Only calculate if a next user pick is found
                    picks_to_simulate = next_user_pick_index - current_pick_num
        else: # Simulation mode
            # Find the next user pick in simulation
            try:
                current_user_pick_index = user_picks_simulation.index(current_pick_num + 1) # +1 because user_picks_simulation is 1-indexed
            except ValueError:
                pass # Current pick is not a user pick, so no next user pick in this sequence

            if current_user_pick_index != -1 and (current_user_pick_index + 1) < len(user_picks_simulation):
                next_user_pick_num = user_picks_simulation[current_user_pick_index + 1]
                picks_to_simulate = (next_user_pick_num - 1) - current_pick_num
            # If no next user pick is found, picks_to_simulate remains 0, which is correct.

        logging.debug(f"VONA Calc Debug: current_pick_num={current_pick_num}, user_picks_simulation={user_picks_simulation}")
        logging.debug(f"VONA Calc Debug: current_user_pick_index={current_user_pick_index}, next_user_pick_num={next_user_pick_num if next_user_pick_num is not None else 'N/A'}")
        logging.info(f"Calculating VONA for {len(available_players)} players, simulating {picks_to_simulate} picks.")

        # Limit VONA calculation to top 50 players by ADP for performance
        players_for_vona = available_players.sort_values(by='ADP').head(50)

        for index, player_row in players_for_vona.iterrows():
            # Create a deep copy of the draft state for a clean simulation
            draft_sim = Draft(draft_obj.players.copy(), draft_obj.format, draft_obj.teams, draft_obj.rounds, draft_obj.roster, draft_obj.order)
            draft_sim.drafted_players = draft_obj.drafted_players.copy()
            teams_list_sim = [Team(roster=t.roster.copy()) for t in teams_list]
            
            vona = calculate_vona(
                player_row, 
                draft_sim, 
                teams_list_sim, 
                picks_to_simulate, 
                draft_obj.teams, 
                current_pick_num, 
                draft_obj.order, 
                original_big_board
            )
            vona_results[player_row['display_name']] = vona
        
        session_state["vona_data"] = vona_results

    @classmethod
    def initialize_draft(
        cls,
        pick_slot: int,
        draft_id: str | None = None,
        non_interactive: bool = False,
        teams: int | None = None,
        rounds: int | None = None,
        format: str | None = None,
        order: str | None = None
    ) -> Dict[str, Any]:
        session_id = str(uuid.uuid4())
        logging.info(f"Initializing draft session: {session_id}")

        # --- Mode Selection ---
        if draft_id:
            # Live Assistant Mode
            logging.info("--- Live Draft Assistant Mode ---")
            draft_settings = sleeper_service.get_draft_settings(draft_id)
            if not draft_settings:
                logging.error("Could not fetch live draft settings.")
                return {"error": "Could not fetch live draft settings."}
            
            draft_teams = draft_settings['teams']
            draft_rounds = draft_settings['rounds']
            draft_format = draft_settings['format']
            draft_order = draft_settings['order']
            user_picks = [] # Not used in live mode
        else:
            # Simulation Mode
            logging.info("--- Draft Simulation Mode ---")
            draft_teams = teams or config.DEFAULT_TEAMS
            draft_rounds = rounds or config.DEFAULT_ROUNDS
            draft_format = (format or config.DEFAULT_DRAFT_FORMAT).upper()
            draft_order = order or 'snake'
            user_picks = get_user_picks(pick_slot, draft_order, draft_teams, draft_rounds)
            logging.info(f"Your simulated picks are at positions: {user_picks}")

        # --- Common Setup ---
        logging.info("Creating big board...")
        big_board = create_vbd_big_board(format=draft_format, teams=draft_teams)
        if big_board.empty:
            logging.error("Big board could not be created.")
            return {"error": "Big board could not be created."}

        # Add sleeper_id to the big board if it's not there, crucial for live mode
        if 'sleeper_id' not in big_board.columns:
            player_data = data_service.load_player_data()[['normalized_name', 'sleeper_id']] # Changed from load_adp_data to load_player_data
            big_board = pd.merge(big_board, player_data, on='normalized_name', how='left')

        draft_obj = Draft(big_board, draft_format, draft_teams, draft_rounds, order=draft_order)
        teams_list = [Team() for _ in range(draft_teams)]

        # Store the draft state
        session_state = {
            "draft_obj": draft_obj,
            "teams_list": teams_list,
            "user_pick_slot": pick_slot,
            "user_picks_simulation": user_picks,
            "draft_id": draft_id,
            "non_interactive": non_interactive,
            "current_pick_num": 0, # Initialize current pick number
            "original_big_board": big_board.copy(), # Keep a copy for VONA/VORP calcs
            "picks_order": [], # Will be populated for live drafts
            "slot_to_roster_id": {}, # Will be populated for live drafts
            "vona_data": {} # Initialize VONA data
        }

        # Populate live draft specific settings if applicable
        if draft_id:
            session_state["picks_order"] = []
            session_state["slot_to_roster_id"] = draft_settings.get('slot_to_roster_id', {})
            user_roster_id = session_state["slot_to_roster_id"].get(str(pick_slot))
            if not user_roster_id:
                logging.error(f"Could not find your roster ID for pick slot {pick_slot}.")
                return {"error": f"Could not find your roster ID for pick slot {pick_slot}."}
            session_state["user_roster_id"] = user_roster_id

            for r in range(1, draft_rounds + 1):
                round_order = list(range(1, draft_teams + 1))
                if draft_order == 'snake' and r % 2 == 0:
                    round_order.reverse()
                session_state["picks_order"].extend(round_order)
        
        cls._active_draft_sessions[session_id] = session_state
        cls._calculate_and_store_vona(session_state) # Calculate initial VONA
        return {"message": "Draft session started.", "session_id": session_id}

    @classmethod
    def get_current_draft_state(cls, session_id: str, position_filter: str | None = None, sort_by: str | None = None) -> Dict[str, Any]:
        session_state = cls._active_draft_sessions.get(session_id)
        if not session_state:
            return {"error": "Draft session not found."}

        draft_obj: Draft = session_state["draft_obj"]
        current_pick_num = session_state["current_pick_num"]
        draft_id = session_state["draft_id"]
        picks_order = session_state["picks_order"]
        slot_to_roster_id = session_state["slot_to_roster_id"]
        user_roster_id = session_state.get("user_roster_id")
        user_picks_simulation = session_state["user_picks_simulation"]
        teams_list = session_state["teams_list"]

        is_user_turn = False
        on_clock_team_info = None
        
        if draft_id:
            # Live mode logic
            if current_pick_num >= len(picks_order):
                return {"message": "Draft appears to be complete.", "status": "completed"}
            
            next_pick_slot = picks_order[current_pick_num]
            on_clock_roster_id = slot_to_roster_id.get(str(next_pick_slot))
            
            if on_clock_roster_id == user_roster_id:
                is_user_turn = True
                on_clock_team_info = {"type": "user", "roster_id": user_roster_id}
            else:
                on_clock_team_info = {"type": "cpu", "roster_id": on_clock_roster_id}
        else:
            # Simulation mode logic
            current_round = (current_pick_num) // draft_obj.teams + 1
            if draft_obj.order == 'snake' and current_round % 2 == 0:
                team_index = draft_obj.teams - ((current_pick_num) % draft_obj.teams) - 1
            else:
                team_index = (current_pick_num) % draft_obj.teams
            
            if (current_pick_num + 1) in user_picks_simulation: # +1 because current_pick_num is 0-indexed
                is_user_turn = True
                on_clock_team_info = {"type": "user", "team_index": team_index}
            else:
                on_clock_team_info = {"type": "cpu", "team_index": team_index}

        # Recalculate VONA if it's the user's turn
        if is_user_turn:
            cls._calculate_and_store_vona(session_state)

        available_players = draft_obj.get_available_players().copy()

        # Apply filtering
        if position_filter and position_filter.upper() != 'ALL':
            if position_filter.upper() == 'FLEX':
                available_players = available_players[available_players['pos'].isin(['RB', 'WR', 'TE'])]
            else:
                available_players = available_players[available_players['pos'] == position_filter.upper()]

        # Apply sorting
        if sort_by:
            ascending = True
            if sort_by.upper() == 'VORP':
                ascending = False # Higher VORP is better
            elif sort_by.upper() == 'ADP':
                ascending = True # Lower ADP is better
            elif sort_by.upper() == 'VONA':
                ascending = False # Higher VONA is better
            
            if sort_by.upper() in available_players.columns:
                available_players = available_players.sort_values(by=sort_by.upper(), ascending=ascending)
            else:
                logging.warning(f"Sort column '{sort_by}' not found in available players. Skipping sort.")

        # Add VONA data to available players for display
        if 'VONA' not in available_players.columns:
            available_players['VONA'] = 0.0 # Initialize VONA column if it doesn't exist
        
        # Merge VONA data from session_state into available_players
        for player_name, vona_value in session_state["vona_data"].items():
            available_players.loc[available_players['display_name'] == player_name, 'VONA'] = vona_value

        # Limit for display after filtering and sorting
        available_players_display = available_players.head(50).to_dict(orient="records")
        
        return {
            "session_id": session_id,
            "current_pick_num": current_pick_num + 1, # Display as 1-indexed
            "is_user_turn": is_user_turn,
            "on_clock_team": on_clock_team_info,
            "available_players": available_players_display,
            "drafted_players_count": len(draft_obj.drafted_players),
            "total_picks": draft_obj.rounds * draft_obj.teams,
            "status": "in_progress"
        }

    @classmethod
    def process_user_pick(cls, session_id: str, player_name: str) -> Dict[str, Any]:
        session_state = cls._active_draft_sessions.get(session_id)
        if not session_state:
            return {"error": "Draft session not found."}

        draft_obj: Draft = session_state["draft_obj"]
        teams_list: List[Team] = session_state["teams_list"]
        current_pick_num = session_state["current_pick_num"]
        draft_id = session_state["draft_id"]
        user_picks_simulation = session_state["user_picks_simulation"]
        
        # Determine current team index based on mode
        team_index = -1
        if draft_id:
            # Live mode: use user_roster_id to find team_index
            user_roster_id = session_state.get("user_roster_id")
            if user_roster_id:
                # This is a simplification; in a real app, you'd map roster_id to your internal team index
                # For now, assuming roster_id directly maps to team_index + 1
                team_index = int(user_roster_id) - 1
        else:
            # Simulation mode
            current_round = (current_pick_num) // draft_obj.teams + 1
            if draft_obj.order == 'snake' and current_round % 2 == 0:
                team_index = draft_obj.teams - ((current_pick_num) % draft_obj.teams) - 1
            else:
                team_index = (current_pick_num) % draft_obj.teams
        
        if team_index == -1:
            return {"error": "Could not determine current team for pick."}

        current_team = teams_list[team_index]
        
        normalized_player_name = normalize_name(player_name)
        pos = draft_obj.draft_player(normalized_player_name)

        if pos:
            current_team.add_player(normalized_player_name, pos)
            session_state["current_pick_num"] += 1
            logging.info(f"User drafted: {player_name} ({pos})")
            cls._calculate_and_store_vona(session_state) # Recalculate VONA after pick
            return {
                "message": f"Successfully drafted {player_name} ({pos}).",
                "player_name": player_name,
                "position": pos,
                "new_pick_num": session_state["current_pick_num"]
            }
        else:
            logging.warning(f"Could not draft '{player_name}'. Player not found or already drafted.")
            return {"error": f"Could not draft '{player_name}'. Player not found or already drafted."}

    @classmethod
    def process_cpu_pick(cls, session_id: str) -> Dict[str, Any]:
        session_state = cls._active_draft_sessions.get(session_id)
        if not session_state:
            return {"error": "Draft session not found."}
        
        draft_obj: Draft = session_state["draft_obj"]
        teams_list: List[Team] = session_state["teams_list"]
        current_pick_num = session_state["current_pick_num"]
        original_big_board = session_state["original_big_board"]
        draft_id = session_state["draft_id"]

        if draft_id:
            return {"error": "CPU picks are only for simulation mode."}

        current_round = (current_pick_num) // draft_obj.teams + 1
        if draft_obj.order == 'snake' and current_round % 2 == 0:
            team_index = draft_obj.teams - ((current_pick_num) % draft_obj.teams) - 1
        else:
            team_index = (current_pick_num) % draft_obj.teams
        
        current_team = teams_list[team_index]
        available_players = draft_obj.get_available_players()

        if available_players.empty:
            return {"message": "No more players available for CPU pick.", "status": "completed"}

        cpu_pick_name = simulate_cpu_pick(available_players, current_team, original_big_board)
        pos = draft_obj.draft_player(normalize_name(cpu_pick_name))

        if pos:
            current_team.add_player(normalize_name(cpu_pick_name), pos)
            session_state["current_pick_num"] += 1
            logging.info(f"CPU (Team {team_index + 1}) drafted: {cpu_pick_name} ({pos}).")
            cls._calculate_and_store_vona(session_state) # Recalculate VONA after pick
            return {
                "message": f"CPU (Team {team_index + 1}) drafted: {cpu_pick_name} ({pos}).",
                "player_name": cpu_pick_name,
                "position": pos,
                "new_pick_num": session_state["current_pick_num"]
            }
        else:
            logging.warning(f"CPU (Team {team_index + 1}) failed to draft a player.")
            return {"error": f"CPU (Team {team_index + 1}) failed to draft a player."}

    @classmethod
    def poll_live_draft_updates(cls, session_id: str) -> Dict[str, Any]:
        session_state = cls._active_draft_sessions.get(session_id)
        if not session_state:
            return {"error": "Draft session not found."}
        
        draft_id = session_state["draft_id"]
        if not draft_id:
            return {"error": "This session is not a live draft."}

        draft_obj: Draft = session_state["draft_obj"]
        original_big_board = session_state["original_big_board"]
        current_pick_num = session_state["current_pick_num"]
        slot_to_roster_id = session_state["slot_to_roster_id"]
        
        all_picks = sleeper_service.get_all_picks(draft_id)
        picks_made = len(all_picks)
        
        new_picks_made = []
        if picks_made > current_pick_num:
            for i in range(current_pick_num, picks_made):
                pick = all_picks[i]
                player_id = pick.get('player_id')
                roster_id = pick.get('roster_id') or slot_to_roster_id.get(str(pick.get('draft_slot')))
                if not player_id or not roster_id: continue
                
                player_info = original_big_board.loc[original_big_board['sleeper_id'] == str(float(player_id))]
                if player_info.empty:
                    logging.warning(f"Player with sleeper_id {player_id} not found in big board.")
                    continue
                
                normalized_name = player_info['normalized_name'].iloc[0]
                display_name = player_info['display_name'].iloc[0]
                pos = player_info['pos'].iloc[0]

                # Only draft if not already drafted (to prevent issues with re-polling)
                if normalized_name not in draft_obj.drafted_players:
                    draft_obj.draft_player(normalized_name)
                    # In live mode, we don't add to teams_list as Sleeper manages rosters
                    new_picks_made.append({
                        "pick_number": i + 1,
                        "roster_id": roster_id,
                        "player_name": display_name,
                        "position": pos
                    })
                    logging.info(f"Live pick {i + 1}: Team {roster_id} drafted {display_name} ({pos})")
                else:
                    logging.info(f"Player {display_name} already marked as drafted.")

            session_state["current_pick_num"] = picks_made
            cls._calculate_and_store_vona(session_state) # Recalculate VONA after live pick
            return {
                "message": f"Found {len(new_picks_made)} new picks.",
                "new_picks": new_picks_made,
                "new_pick_num": session_state["current_pick_num"]
            }
        else:
            return {"message": "No new picks found.", "new_picks": []}
