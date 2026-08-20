import pandas as pd
from typing import List, Dict, Any
import uuid
import logging

from backend.services.draft import Draft, Team
from backend import config, league, keepers as keeper_files
from backend.draft_order import DraftOrder, PickBook, PLAIN_SNAKE_FROM
from backend.services.vbd_service import create_vbd_big_board, calculate_vona_board
from backend.services.simulation_service import simulate_cpu_pick, simulate_user_auto_pick
from backend.services import sleeper_service, data_service
from backend.utils import normalize_name, normalize_scoring_format, points_column

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def _json_safe_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Converts a DataFrame to records with every NaN replaced by None.

    json.dumps serializes float('nan') as a bare NaN literal, which JSON.parse
    rejects, so a single missing ADP or projection in the response would break the
    whole draft board.
    """
    return df.astype(object).where(pd.notna(df), None).to_dict(orient="records")


def _roster_and_conflicts(
    team: Team, board: pd.DataFrame
) -> tuple[List[Dict[str, Any]], Dict[int, List[str]]]:
    """
    The team's roster as display rows, plus its bye-week conflicts.

    Both come back together because both need the same normalized-name-to-display-
    name lookup off the board -- Team.roster holds normalized names. The conflict
    *rule* stays on Team, which is the only thing that knows the byes; this just
    renames the output so a warning and the roster beneath it do not disagree about
    what a player is called.
    """
    if board is None or board.empty:
        lookup: Dict[str, Dict[str, Any]] = {}
    else:
        deduped = board.drop_duplicates(subset=["normalized_name"], keep="first")
        lookup = deduped.set_index("normalized_name")[["display_name", "pos"]].to_dict("index")

    def display(player: str) -> str:
        return lookup.get(player, {}).get("display_name", player)

    rows = [
        {
            "slot": slot,
            "player": display(player) if player else None,
            "pos": lookup.get(player, {}).get("pos") if player else None,
            # Bye comes off the Team rather than the board: the Team is what was
            # told the bye at pick time, and is what the conflict check reads.
            "bye": team.bye_week(player) if player else None,
        }
        for slot, player in team.roster.items()
    ]

    conflicts = {
        week: [display(p) for p in players]
        for week, players in team.bye_conflicts().items()
    }
    return rows, conflicts


class DraftManagerService:
    _active_draft_sessions: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def _user_team(cls, session_state: Dict[str, Any]) -> Team | None:
        """
        The user's own Team, in either mode.

        Simulation indexes teams_list by draft slot; live mode indexes it by roster
        id, which is the mapping the rest of the live code already assumes.
        """
        teams_list: List[Team] = session_state["teams_list"]

        if session_state["draft_id"]:
            user_roster_id = session_state.get("user_roster_id")
            if not user_roster_id:
                return None
            index = int(user_roster_id) - 1
        else:
            index = session_state["user_pick_slot"] - 1

        return teams_list[index] if 0 <= index < len(teams_list) else None

    @classmethod
    def _is_complete(cls, session_state: Dict[str, Any]) -> bool:
        """
        Whether every pick in the draft has been made.

        Only live mode used to check this, against `len(picks_order)` -- which is
        the same number, since picks_order is built round by round. Simulation had
        no bound at all, so "Simulate next pick" kept drafting past the final round
        until the player pool ran dry, hundreds of picks later.
        """
        draft_obj: Draft = session_state["draft_obj"]
        return session_state["current_pick_num"] >= draft_obj.rounds * draft_obj.teams

    @classmethod
    def _calculate_and_store_vona(cls, session_state: Dict[str, Any]):
        draft_obj: Draft = session_state["draft_obj"]
        teams_list: List[Team] = session_state["teams_list"]
        current_pick_num = session_state["current_pick_num"]
        user_picks_simulation = session_state["user_picks_simulation"]
        draft_id = session_state["draft_id"]
        user_pick_slot = session_state["user_pick_slot"]
        picks_order = session_state["picks_order"]
        slot_to_roster_id = session_state["slot_to_roster_id"]

        available_players = draft_obj.get_available_players().copy()

        # Nothing left to value: no board, or no pick of yours left to value it for.
        if available_players.empty or cls._is_complete(session_state):
            session_state["vona_data"] = {}
            session_state["gone_data"] = {}
            session_state["vona_computed_for"] = cls._vona_state_key(session_state)
            return

        # How many picks stand between now and the user's next turn. That span is
        # the whole of VONA: it is what the player has to survive to still be
        # there when the user picks.
        picks_to_simulate = 0
        next_user_pick_num = None # Initialize to None
        upcoming_owners = None    # Simulation mode only; live mode has no pick book

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
            # The first pick of yours that is still ahead of the pick on the clock.
            # On your turn that is the pick *after* this one, so VONA is the cost
            # of passing; off-turn it is the turn you are waiting for, and the
            # picks in between are the ones that can take him.
            #
            # This used to look the pick on the clock up in user_picks_simulation
            # and give up when it was not there, which meant VONA existed only on
            # the user's own turn -- every other pick left the column a board of
            # zeroes that the room had to grey out rather than print. Both live
            # mode and this one now ask the same question, and it is a question
            # with an answer whoever is on the clock.
            pick_on_clock = current_pick_num + 1 # user_picks_simulation is 1-indexed
            next_user_pick_num = next(
                (pick for pick in user_picks_simulation if pick > pick_on_clock), None
            )
            if next_user_pick_num is not None:
                # The picks actually made between here and your turn, as a
                # sequence of teams rather than a count. Both halves matter now
                # that a league has keepers: a kept pick in the span is already
                # made, so simulating it would drain a player who is not going
                # anywhere, and a traded pick belongs to a different roster, so
                # simulating it against the wrong team reads the wrong needs.
                pick_book: PickBook = session_state["pick_book"]
                upcoming_owners = pick_book.open_picks_between(
                    current_pick_num, next_user_pick_num - 1
                )
                picks_to_simulate = len(upcoming_owners)
            # No pick of yours left to wait for: picks_to_simulate stays 0, which
            # calculate_vona_board reads as "waiting costs nothing".

        logging.debug(f"VONA Calc Debug: current_pick_num={current_pick_num}, user_picks_simulation={user_picks_simulation}")
        logging.debug(f"VONA Calc Debug: next_user_pick_num={next_user_pick_num if next_user_pick_num is not None else 'N/A'}")
        logging.info(f"Calculating VONA for {len(available_players)} players, simulating {picks_to_simulate} picks.")

        # One shared set of simulations scores the entire board, so there is no
        # longer any reason to cap this at the top 50 by ADP.
        waiting = calculate_vona_board(
            available_players,
            draft_obj,
            teams_list,
            picks_to_simulate,
            current_pick_num,
            pick_owners=upcoming_owners,
        )

        # Two readings of the same simulations. The cost is what waiting is worth
        # in points; the probability is the raw "will he last?" behind it, which is
        # worth showing on its own -- a big cost driven by a 20% chance of losing
        # someone is a very different pick than the same cost at 95%.
        session_state["vona_data"] = waiting.cost
        session_state["gone_data"] = waiting.gone
        session_state["vona_computed_for"] = cls._vona_state_key(session_state)

    @staticmethod
    def _vona_state_key(session_state: Dict[str, Any]) -> tuple:
        """Identifies the board state VONA was computed against."""
        return (session_state["current_pick_num"], len(session_state["draft_obj"].drafted_players))

    @classmethod
    def _ensure_vona(cls, session_state: Dict[str, Any]):
        """
        Recomputes VONA only when the board has actually moved.

        get_current_draft_state recalculates on every request while it is the
        user's turn, so changing a filter or letting the live room poll used to
        pay the full simulation cost again for an unchanged board.
        """
        if session_state.get("vona_computed_for") == cls._vona_state_key(session_state):
            return
        cls._calculate_and_store_vona(session_state)

    @staticmethod
    def _build_pick_book(
        teams: int, rounds: int, order: str, snake_from: int | None,
        big_board: pd.DataFrame, use_keepers: bool,
    ) -> PickBook:
        """
        Who owns every pick, and which are already spent.

        Built even when the league has no keepers and no trades, because it is
        also what replaced the snake arithmetic: one lookup table instead of the
        same `current_round % 2` reimplemented in four places, none of which could
        express a traded pick or a draft that starts snaking anywhere but round 2.

        `snake_from` is the first round that runs backwards -- 2 is a plain snake
        and is the default, so a league that says nothing drafts exactly as before.
        """
        draft_order = (
            DraftOrder.straight(teams, rounds) if order != 'snake'
            else DraftOrder(teams, rounds, snake_from or PLAIN_SNAKE_FROM)
        )

        book = (
            keeper_files.load(config.DATA_DIR) if use_keepers
            else keeper_files.LeagueBook()
        )
        if book:
            logging.info("League files: %s.", book.describe())

        board_names = dict(zip(big_board['normalized_name'], big_board['display_name']))
        return keeper_files.build_pick_book(draft_order, book, board_names)

    @staticmethod
    def _seat_keepers(draft_obj: Draft, teams_list: List[Team], pick_book: PickBook) -> None:
        """
        Puts every kept player on his roster before the draft opens.

        All of them at once, rather than each when its pick comes round, because
        that is what is actually true: everybody knows who is kept, so none of
        them is available at pick one and no valuation should pretend otherwise.
        It also lands `Team.picks_made` on the right number from the start, which
        is what the CPU's endgame logic reads.
        """
        for keeper in pick_book.keepers():
            pos = draft_obj.draft_player(keeper.normalized_name)
            if not pos:
                # build_pick_book already rejected anything off the board, so this
                # is only reachable if two keepers named the same player.
                logging.warning("Keeper %s could not be seated.", keeper.player)
                continue
            teams_list[keeper.team_index].add_player(
                keeper.normalized_name, pos, draft_obj.player_bye(keeper.normalized_name)
            )

    @classmethod
    def _keeper_rows(cls, session_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Every kept player, as the draft sheet reads: round, seat, and who has him."""
        pick_book: PickBook = session_state.get("pick_book")
        if pick_book is None:
            return []

        user_index = session_state["user_pick_slot"] - 1
        order = pick_book.order
        return [
            {
                "round": order.round_of(keeper.pick_index),
                "pick": order.slot_at(keeper.pick_index),
                "overall": keeper.pick_index + 1,
                "player": keeper.player,
                "manager": keeper.manager,
                "is_user": keeper.team_index == user_index,
            }
            for keeper in pick_book.keepers()
        ]

    @classmethod
    def _team_on_clock(cls, session_state: Dict[str, Any]) -> int:
        """
        The 0-based index into `teams_list` of whoever is picking, in either mode.

        One place. This was the snake calculation, copied into
        `get_current_draft_state`, `process_user_pick`, `process_cpu_pick` and
        `process_auto_pick_helper` -- and a copy of a formula cannot represent a
        pick that changed hands, nor a draft that starts snaking anywhere but
        round two.

        Live mode indexes `teams_list` by roster id rather than by seat, which is
        the other thing the copies got wrong: `process_auto_pick_helper` used the
        snake index against a live draft, so any league whose roster ids are not
        in seat order auto-picked onto somebody else's roster.
        """
        if session_state["draft_id"]:
            picks_order = session_state["picks_order"]
            index = session_state["current_pick_num"]
            if not 0 <= index < len(picks_order):
                return -1
            roster_id = session_state["slot_to_roster_id"].get(str(picks_order[index]))
            return int(roster_id) - 1 if roster_id else -1

        pick_book: PickBook = session_state["pick_book"]
        return pick_book.owner_of(session_state["current_pick_num"])

    @classmethod
    def _advance_clock(cls, session_state: Dict[str, Any]) -> None:
        """Moves to the next pick somebody actually makes, stepping over keepers."""
        pick_book: PickBook = session_state.get("pick_book")
        nxt = session_state["current_pick_num"] + 1
        session_state["current_pick_num"] = (
            pick_book.next_open_pick(nxt) if pick_book is not None else nxt
        )

    @classmethod
    def initialize_draft(
        cls,
        pick_slot: int,
        draft_id: str | None = None,
        non_interactive: bool = False,
        teams: int | None = None,
        rounds: int | None = None,
        format: str | None = None,
        order: str | None = None,
        scoring: Dict[str, Any] | None = None,
        roster: Dict[str, Any] | None = None,
        snake_from: int | None = None,
        use_keepers: bool = True,
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
            draft_format = normalize_scoring_format(format, default=config.DEFAULT_DRAFT_FORMAT)
            draft_order = order or 'snake'
            # Deferred: which picks are yours depends on the traded ones and on
            # which are already spent on keepers, and resolving keepers needs the
            # board. Built below, once there is one.
            user_picks = []

        # --- League settings ---
        # The format is still what picks the ADP column, and seeds the scoring
        # defaults. Anything the league does differently -- six-point passing
        # touchdowns, a tight-end premium, a superflex -- comes in here and is
        # what the board is actually built from.
        try:
            league_scoring = league.ScoringSettings.for_format(draft_format).with_overrides(scoring)
            league_roster = league.RosterSettings.from_payload(teams=draft_teams, roster=roster)
        except (ValueError, TypeError) as error:
            logging.error(f"Invalid league settings: {error}")
            return {"error": f"Invalid league settings: {error}"}

        # --- Common Setup ---
        logging.info("Creating big board...")
        big_board = create_vbd_big_board(
            format=draft_format, teams=draft_teams,
            scoring=league_scoring, roster=league_roster,
        )
        if big_board.empty:
            logging.error("Big board could not be created.")
            return {"error": "Big board could not be created."}

        # Add sleeper_id to the big board if it's not there, crucial for live mode
        if 'sleeper_id' not in big_board.columns:
            player_data = data_service.load_player_data()[['normalized_name', 'sleeper_id']] # Changed from load_adp_data to load_player_data
            big_board = pd.merge(big_board, player_data, on='normalized_name', how='left')

        # The bench is sized from the round count. Left at the module default, a
        # 20-round draft had two picks with no slot to sit in and a 10-round draft
        # showed eight bench rows nobody could ever fill.
        slots = league_roster.slots(draft_rounds)
        draft_obj = Draft(big_board, draft_format, draft_teams, draft_rounds, roster=slots, order=draft_order)
        teams_list = [Team(slots) for _ in range(draft_teams)]

        # --- Keepers and traded picks ---
        # Simulation only. A live draft gets its picks from Sleeper, which already
        # knows who was kept, so applying them here as well would count them twice.
        pick_book = None
        if not draft_id:
            try:
                pick_book = cls._build_pick_book(
                    draft_teams, draft_rounds, draft_order, snake_from,
                    big_board, use_keepers,
                )
            except (ValueError, KeyError, IndexError) as error:
                # Refusing to start is the point. A keeper that silently fails to
                # apply leaves the player on the board *and* leaves his pick live,
                # and both errors compound quietly for the rest of the draft.
                logging.error("Could not apply the league's keepers: %s", error)
                return {"error": f"Could not apply the league's keepers: {error}"}

            cls._seat_keepers(draft_obj, teams_list, pick_book)
            keeper_files.log_pick_book(pick_book)

            user_picks = pick_book.picks_for(pick_slot - 1)
            logging.info(f"Your picks are at positions: {user_picks}")

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
            "vona_data": {}, # Expected points lost by waiting, per player
            "gone_data": {}, # Probability of being gone by your next turn
            # The league this board was built for. Kept so anything that
            # recomputes later values players by the same rules the board did.
            "scoring": league_scoring,
            "roster_settings": league_roster,
            # Who owns each pick and which are already spent on keepers. None in
            # live mode, where Sleeper's picks_order is the equivalent.
            "pick_book": pick_book,
        }

        # The clock never rests on a pick nobody makes. Every keeper is already
        # applied, so if the draft opens on one -- and with a keeper at 1.01 it
        # does -- the first live pick is further down the board.
        if pick_book is not None:
            session_state["current_pick_num"] = pick_book.next_open_pick(0)

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

        # A finished draft still returns the whole payload -- the board it ended on
        # and, more to the point, the roster you ended up with. Live mode used to
        # bail out with a bare status here, which left the room with no
        # `on_clock_team` to render and no roster to show for the draft you just did.
        is_complete = cls._is_complete(session_state)

        # Nobody is on the clock once the draft is over, in either mode.
        if not is_complete:
            if draft_id:
                # Live mode logic
                next_pick_slot = picks_order[current_pick_num]
                on_clock_roster_id = slot_to_roster_id.get(str(next_pick_slot))

                if on_clock_roster_id == user_roster_id:
                    is_user_turn = True
                    on_clock_team_info = {"type": "user", "roster_id": user_roster_id}
                else:
                    on_clock_team_info = {"type": "cpu", "roster_id": on_clock_roster_id}
            else:
                # Simulation mode logic
                team_index = cls._team_on_clock(session_state)

                if (current_pick_num + 1) in user_picks_simulation: # +1 because current_pick_num is 0-indexed
                    is_user_turn = True
                    on_clock_team_info = {"type": "user", "team_index": team_index}
                else:
                    on_clock_team_info = {"type": "cpu", "team_index": team_index}

        # VONA is worth reading while you wait, not only while you are on the
        # clock -- off the clock it answers "who is still going to be there when I
        # pick", which is exactly what you are sitting there wondering. _ensure_vona
        # is what keeps that affordable: this endpoint is hit on every filter
        # change and every live-draft poll, and it recomputes only when the board
        # has actually moved.
        cls._ensure_vona(session_state)

        available_players = draft_obj.get_available_players().copy()

        # Apply filtering
        if position_filter and position_filter.upper() != 'ALL':
            if position_filter.upper() == 'FLEX':
                available_players = available_players[available_players['pos'].isin(['RB', 'WR', 'TE'])]
            else:
                available_players = available_players[available_players['pos'] == position_filter.upper()]

        # Attach VONA *before* sorting. Sorting first meant the VONA column did not
        # exist yet, so "Sort By: VONA" silently fell through to the warning below
        # and returned the board in its existing order.
        available_players['VONA'] = (
            available_players['display_name'].map(session_state["vona_data"]).fillna(0.0)
        )
        # The chance he is gone before your next turn, 0-1. It is the other half of
        # VONA and it answers a question VONA cannot on its own: a player can be
        # worth a lot more than the next man down and still be nearly certain to
        # last, which is exactly when you should be taking somebody else.
        available_players['GONE'] = (
            available_players['display_name'].map(session_state.get("gone_data", {})).fillna(0.0)
        )

        # The season projection, under a name the frontend can rely on. The column
        # it actually lives in is format-specific -- fantasy_points_half_ppr and so
        # on -- and the scoring format is not something the room is told.
        #
        # Copied rather than renamed: VORP is derived from this column and the CPU
        # simulation reads it off the same board by its real name.
        proj_column = points_column(draft_obj.format)
        available_players['PTS'] = (
            available_players[proj_column]
            if proj_column in available_players.columns
            else float('nan')
        )

        # Apply sorting
        if sort_by:
            ascending = True
            if sort_by.upper() == 'VORP':
                ascending = False # Higher VORP is better
            elif sort_by.upper() == 'ADP':
                ascending = True # Lower ADP is better
            elif sort_by.upper() == 'VONA':
                ascending = False # Higher VONA is better
            elif sort_by.upper() == 'PTS':
                ascending = False # Higher projection is better

            if sort_by.upper() in available_players.columns:
                available_players = available_players.sort_values(by=sort_by.upper(), ascending=ascending)
            else:
                logging.warning(f"Sort column '{sort_by}' not found in available players. Skipping sort.")

        # Limit for display after filtering and sorting
        available_players_display = _json_safe_records(available_players.head(50))

        user_team = cls._user_team(session_state)
        user_roster, bye_conflicts = (
            _roster_and_conflicts(user_team, session_state["original_big_board"])
            if user_team else ([], {})
        )

        return {
            "session_id": session_id,
            # 1-indexed for display, but clamped: once the last pick is in,
            # current_pick_num equals the total, and +1 reads as "pick 241 / 240".
            "current_pick_num": min(current_pick_num + 1, draft_obj.rounds * draft_obj.teams),
            "is_user_turn": is_user_turn,
            "on_clock_team": on_clock_team_info,
            "available_players": available_players_display,
            "drafted_players_count": len(draft_obj.drafted_players),
            "total_picks": draft_obj.rounds * draft_obj.teams,
            # League size and length, so the rail can show a round number without
            # guessing -- total_picks is their product and recovers neither alone.
            "teams": draft_obj.teams,
            "rounds": draft_obj.rounds,
            "user_roster": user_roster,
            # {week: [player, ...]} for weeks that would sideline two or more of the
            # user's players at once.
            "bye_conflicts": bye_conflicts,
            # The picks nobody makes. The room needs these to explain a draft
            # that opens at pick 4 and jumps from 20 to 25 -- without them the
            # numbering looks broken rather than kept.
            "keepers": cls._keeper_rows(session_state),
            "status": "completed" if is_complete else "in_progress"
        }

    @classmethod
    def process_user_pick(cls, session_id: str, player_name: str) -> Dict[str, Any]:
        session_state = cls._active_draft_sessions.get(session_id)
        if not session_state:
            return {"error": "Draft session not found."}

        if cls._is_complete(session_state):
            return {"error": "The draft is complete.", "status": "completed"}

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
            team_index = cls._team_on_clock(session_state)

        if team_index == -1:
            return {"error": "Could not determine current team for pick."}

        current_team = teams_list[team_index]
        
        normalized_player_name = normalize_name(player_name)
        pos = draft_obj.draft_player(normalized_player_name)

        if pos:
            current_team.add_player(normalized_player_name, pos, draft_obj.player_bye(normalized_player_name))
            cls._advance_clock(session_state)
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
        draft_id = session_state["draft_id"]

        if draft_id:
            return {"error": "CPU picks are only for simulation mode."}

        # Without this the button kept working after the final round, cycling the
        # team index round the board and draining the player pool.
        if cls._is_complete(session_state):
            return {"error": "The draft is complete.", "status": "completed"}

        team_index = cls._team_on_clock(session_state)
        current_team = teams_list[team_index]
        available_players = draft_obj.get_available_players()

        if available_players.empty:
            return {"message": "No more players available for CPU pick.", "status": "completed"}

        # Its *own* remaining picks, not `rounds - picks_made`. A manager who
        # traded three away has twelve in a fifteen-round draft, and on the old
        # count never reached the window where the CPU fills its kicker and
        # defense slots -- so it finished the draft without either.
        pick_book: PickBook = session_state["pick_book"]
        cpu_pick_name = simulate_cpu_pick(
            available_players, current_team, draft_obj.rounds,
            picks_remaining=pick_book.picks_remaining(team_index, current_pick_num),
        )
        pos = draft_obj.draft_player(normalize_name(cpu_pick_name))

        if pos:
            normalized_cpu_name = normalize_name(cpu_pick_name)
            current_team.add_player(normalized_cpu_name, pos, draft_obj.player_bye(normalized_cpu_name))
            cls._advance_clock(session_state)
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
                
                # Sleeper sends numeric ids for players ("4034") but the team
                # abbreviation for defenses ("DEN"). The board stores player ids in
                # float-string form ("4034.0") and defenses as the abbreviation, so
                # try both rather than letting float() raise on a defense.
                candidate_ids = [str(player_id)]
                try:
                    candidate_ids.insert(0, str(float(player_id)))
                except (TypeError, ValueError):
                    pass

                player_info = original_big_board.loc[original_big_board['sleeper_id'].isin(candidate_ids)]
                if player_info.empty:
                    logging.warning(f"Player with sleeper_id {player_id} not found in big board.")
                    continue
                
                normalized_name = player_info['normalized_name'].iloc[0]
                display_name = player_info['display_name'].iloc[0]
                pos = player_info['pos'].iloc[0]

                # Only draft if not already drafted (to prevent issues with re-polling)
                if normalized_name not in draft_obj.drafted_players:
                    draft_obj.draft_player(normalized_name)
                    # Sleeper owns the opponents' rosters, so teams_list stays empty
                    # for them. The user's own team is tracked anyway -- it is what
                    # the bye-conflict warning reads, and that warning is worth more
                    # in a live draft than in a simulation.
                    if str(roster_id) == str(session_state.get("user_roster_id")):
                        user_team = cls._user_team(session_state)
                        if user_team:
                            user_team.add_player(
                                normalized_name, pos, draft_obj.player_bye(normalized_name)
                            )
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

    @classmethod
    def calculate_vona_for_display(cls, session_id: str, player_names: List[str]) -> Dict[str, Any]:
        session_state = cls._active_draft_sessions.get(session_id)
        if not session_state:
            return {"error": "Draft session not found."}

        vona_data = session_state.get("vona_data", {})
        results = {name: vona_data.get(name, 0) for name in player_names}
        return results

    @classmethod
    def initialize_draft_helper(
        cls,
        pick_slot: int,
        draft_id: str | None = None,
        non_interactive: bool = False,
        teams: int | None = None,
        rounds: int | None = None,
        format: str | None = None,
        order: str | None = None,
        scoring: Dict[str, Any] | None = None,
        roster: Dict[str, Any] | None = None,
        snake_from: int | None = None,
        use_keepers: bool = True,
    ) -> Dict[str, Any]:
        return cls.initialize_draft(
            pick_slot,
            draft_id,
            non_interactive,
            teams,
            rounds,
            format,
            order,
            scoring,
            roster,
            snake_from,
            use_keepers,
        )

    @classmethod
    def get_current_draft_helper_state(cls, session_id: str, position_filter: str | None = None, sort_by: str | None = None) -> Dict[str, Any]:
        return cls.get_current_draft_state(session_id, position_filter, sort_by)

    @classmethod
    def process_user_pick_helper(cls, session_id: str, player_name: str) -> Dict[str, Any]:
        return cls.process_user_pick(session_id, player_name)

    @classmethod
    def process_cpu_pick_helper(cls, session_id: str) -> Dict[str, Any]:
        return cls.process_cpu_pick(session_id)

    @classmethod
    def process_auto_pick_helper(cls, session_id: str) -> Dict[str, Any]:
        session_state = cls._active_draft_sessions.get(session_id)
        if not session_state:
            return {"error": "Draft session not found."}

        if cls._is_complete(session_state):
            return {"error": "The draft is complete.", "status": "completed"}

        draft_obj: Draft = session_state["draft_obj"]
        teams_list: List[Team] = session_state["teams_list"]
        current_pick_num = session_state["current_pick_num"]

        team_index = cls._team_on_clock(session_state)
        if team_index == -1:
            return {"error": "Could not determine current team for pick."}

        current_team = teams_list[team_index]
        available_players = draft_obj.get_available_players().copy()

        if available_players.empty:
            return {"message": "No more players available for auto pick.", "status": "completed"}

        # simulate_user_auto_pick ranks on VONA, which lives in the session rather
        # than on the board -- get_current_draft_state attaches it to its own copy.
        # Without this the endpoint raised KeyError: 'VONA' on every call.
        cls._ensure_vona(session_state)
        available_players['VONA'] = (
            available_players['display_name'].map(session_state["vona_data"]).fillna(0.0)
        )

        pick_book: PickBook = session_state.get("pick_book")
        player_name = simulate_user_auto_pick(
            available_players, current_team, draft_obj.rounds,
            picks_remaining=(
                pick_book.picks_remaining(team_index, current_pick_num)
                if pick_book is not None else None
            ),
        )
        pos = draft_obj.draft_player(normalize_name(player_name))

        if pos:
            normalized_auto_name = normalize_name(player_name)
            current_team.add_player(normalized_auto_name, pos, draft_obj.player_bye(normalized_auto_name))
            cls._advance_clock(session_state)
            logging.info(f"Auto-drafting: {player_name} ({pos})")
            cls._calculate_and_store_vona(session_state)
            return {
                "message": f"Successfully auto-drafted {player_name} ({pos}).",
                "player_name": player_name,
                "position": pos,
                "new_pick_num": session_state["current_pick_num"]
            }
        else:
            logging.warning(f"Could not auto-draft '{player_name}'. Player not found or already drafted.")
            return {"error": f"Could not auto-draft '{player_name}'. Player not found or already drafted."}

    @classmethod
    def poll_live_draft_updates_helper(cls, session_id: str) -> Dict[str, Any]:
        return cls.poll_live_draft_updates(session_id)
