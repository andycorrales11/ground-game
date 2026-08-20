"""
Tests for DraftManagerService, driven off a synthetic session so they need no
database and no running Sleeper draft.

process_auto_pick_helper is the one method on this service that is not a passthrough
to its simulation counterpart, and it is the live room's "pick for me" button.
"""
import numpy as np
import pytest

from backend import config
from backend.services.draft import Draft, Team
from backend.services.draft_manager_service import DraftManagerService as DMS
from backend.services.vbd_service import WaitingCost
from backend.draft_order import DraftOrder, KeptPlayer, PickBook
from backend import keepers as keeper_files
from backend.tests.boards import make_board


TEAMS = 12


@pytest.fixture(autouse=True)
def _seeded_rng():
    np.random.seed(0)


@pytest.fixture
def session():
    """A simulation session at pick 1, wired up the way initialize_draft wires one."""
    board = make_board()
    draft_obj = Draft(board.copy(), 'PPR', TEAMS, 15, order='snake')
    pick_book = PickBook(DraftOrder(TEAMS, 15))
    state = {
        "draft_obj": draft_obj,
        "teams_list": [Team() for _ in range(TEAMS)],
        "user_pick_slot": 1,
        "user_picks_simulation": [1, 24, 25, 48],
        "pick_book": pick_book,
        "draft_id": None,
        "non_interactive": True,
        "current_pick_num": 0,
        "original_big_board": board.copy(),
        "picks_order": [],
        "slot_to_roster_id": {},
        "vona_data": {},
    }
    session_id = "test-session"
    DMS._active_draft_sessions[session_id] = state
    yield session_id, state
    DMS._active_draft_sessions.pop(session_id, None)


def test_auto_pick_returns_a_player(session):
    """
    Regression: this raised KeyError: 'VONA' on every call, so the endpoint 500'd.

    simulate_user_auto_pick ranks on a VONA column that only get_current_draft_state
    ever attached, and it attached it to its own copy of the board.
    """
    session_id, state = session

    result = DMS.process_auto_pick_helper(session_id)

    assert "error" not in result, result
    assert result["player_name"] in set(state["original_big_board"]['display_name'])
    assert result["position"] in ('QB', 'RB', 'WR', 'TE', 'K')
    assert result["new_pick_num"] == 1
    assert len(state["draft_obj"].drafted_players) == 1


def test_auto_pick_is_actually_ranked_on_vona(session):
    """The VONA weight is 0.5 of the auto-pick score, so it has to change the pick."""
    session_id, state = session

    # Pre-seed VONA and mark it current so _ensure_vona leaves it alone.
    state["vona_data"] = {"RB2": 100.0}
    state["vona_computed_for"] = DMS._vona_state_key(state)

    assert DMS.process_auto_pick_helper(session_id)["player_name"] == "RB2"


def test_auto_pick_without_vona_does_not_choose_rb2(session):
    """Control for the test above: RB2 is not what a flat board would return."""
    session_id, state = session

    state["vona_data"] = {}
    state["vona_computed_for"] = DMS._vona_state_key(state)

    assert DMS.process_auto_pick_helper(session_id)["player_name"] != "RB2"


def test_auto_pick_records_the_position_on_the_roster(session):
    """
    The pick has to land on the drafting team, or the CPU's positional logic is
    reasoning about an empty roster for the rest of the draft.
    """
    session_id, state = session

    result = DMS.process_auto_pick_helper(session_id)
    team = state["teams_list"][0]

    assert team.count_players_at_position(result["position"]) == 1
    assert result["player_name"].lower() in team.roster.values()


def test_auto_pick_reports_an_empty_board(session):
    session_id, state = session
    draft_obj = state["draft_obj"]
    draft_obj.drafted_players = set(draft_obj.players['normalized_name'])

    result = DMS.process_auto_pick_helper(session_id)

    assert result["status"] == "completed"


# --- Draft completion -------------------------------------------------------
#
# A simulation had no end. Only live mode bounded itself, against len(picks_order);
# simulation just kept incrementing current_pick_num, cycling the team index round
# the board on the modulo, and "Simulate next pick" drafted until the pool ran dry
# -- hundreds of picks past the final round.

SMALL_TEAMS = 2
SMALL_ROUNDS = 3


@pytest.fixture
def short_session():
    """A 2-team, 3-round simulation: six picks and then it is over."""
    board = make_board()
    slots = config.roster_slots(SMALL_ROUNDS)
    draft_obj = Draft(board.copy(), 'PPR', SMALL_TEAMS, SMALL_ROUNDS, roster=slots, order='snake')
    pick_book = PickBook(DraftOrder(SMALL_TEAMS, SMALL_ROUNDS))
    state = {
        "draft_obj": draft_obj,
        "teams_list": [Team(slots) for _ in range(SMALL_TEAMS)],
        "user_pick_slot": 1,
        "user_picks_simulation": pick_book.picks_for(0),
        "pick_book": pick_book,
        "draft_id": None,
        "non_interactive": True,
        "current_pick_num": 0,
        "original_big_board": board.copy(),
        "picks_order": [],
        "slot_to_roster_id": {},
        "vona_data": {},
    }
    session_id = "test-short-session"
    DMS._active_draft_sessions[session_id] = state
    yield session_id, state
    DMS._active_draft_sessions.pop(session_id, None)


def _run_out_the_draft(session_id, state):
    """Auto-picks every pick in the draft, and returns the number made."""
    total = SMALL_TEAMS * SMALL_ROUNDS
    for _ in range(total):
        assert "error" not in DMS.process_auto_pick_helper(session_id)
    return state["current_pick_num"]


def test_simulating_past_the_final_pick_is_refused(short_session):
    session_id, state = short_session
    total = SMALL_TEAMS * SMALL_ROUNDS
    assert _run_out_the_draft(session_id, state) == total

    result = DMS.process_cpu_pick(session_id)

    assert result["status"] == "completed"
    assert "error" in result
    # The refusal has to be a no-op, not just a message: the board and the pick
    # counter both have to stay where the last real pick left them.
    assert state["current_pick_num"] == total
    assert len(state["draft_obj"].drafted_players) == total


def test_user_and_auto_picks_are_refused_after_the_final_pick(short_session):
    session_id, state = short_session
    _run_out_the_draft(session_id, state)
    remaining = state["draft_obj"].get_available_players()['display_name'].iloc[0]

    assert DMS.process_user_pick(session_id, remaining)["status"] == "completed"
    assert DMS.process_auto_pick_helper(session_id)["status"] == "completed"
    assert state["current_pick_num"] == SMALL_TEAMS * SMALL_ROUNDS


def test_completed_state_still_carries_the_board_and_roster(short_session):
    """
    The end of a draft is when you most want to look at what you drafted.

    Live mode used to return a bare {"message", "status"} here, which left the room
    with no on-clock team to render and no roster to show.
    """
    session_id, state = short_session
    _run_out_the_draft(session_id, state)

    result = DMS.get_current_draft_state(session_id)

    assert result["status"] == "completed"
    assert result["is_user_turn"] is False
    assert result["on_clock_team"] is None
    # Pick 6 of 6, not 7 of 6.
    assert result["current_pick_num"] == result["total_picks"] == SMALL_TEAMS * SMALL_ROUNDS
    assert result["available_players"]
    assert [slot for slot in result["user_roster"] if slot["player"]]


def test_board_carries_the_season_projection(short_session):
    """
    PTS is a stable alias for a format-specific column.

    The projection lives in fantasy_points_ppr / _half_ppr / _std depending on the
    league, and the room is never told which scoring format the session uses -- so
    without the alias the frontend would have to guess the column name.
    """
    session_id, state = short_session
    board = state["original_big_board"].set_index('display_name')

    rows = DMS.get_current_draft_state(session_id)["available_players"]

    projected = [row for row in rows if row["PTS"] is not None]
    assert projected
    for row in projected:
        assert row["PTS"] == pytest.approx(board.loc[row["display_name"], 'fantasy_points_ppr'])


def test_board_sorts_by_projection_descending(short_session):
    """Higher is better, unlike ADP -- and the sort default is ascending."""
    session_id, _ = short_session

    rows = DMS.get_current_draft_state(session_id, sort_by='PTS')["available_players"]
    points = [row["PTS"] for row in rows]
    projected = [pts for pts in points if pts is not None]

    assert projected == sorted(projected, reverse=True)
    # Unprojected players sort last rather than to the top, which is the same
    # rule the rest of the board follows -- no projection is not a low score.
    assert points[: len(projected)] == projected


def test_unprojected_players_carry_a_null_projection(short_session):
    """
    The synthetic kickers have no projection, exactly as the real board's do.

    NaN has to reach the response as null: json.dumps writes a bare NaN literal
    that JSON.parse rejects, and a 0.0 would read as a real projection of zero.
    """
    session_id, _ = short_session

    rows = DMS.get_current_draft_state(session_id)["available_players"]
    kickers = [row for row in rows if row["pos"] == 'K']

    assert kickers
    assert all(row["PTS"] is None for row in kickers)


def test_state_reports_league_size(short_session):
    """The rail derives the round number from these, and omits it without them."""
    session_id, _ = short_session

    result = DMS.get_current_draft_state(session_id)

    assert result["teams"] == SMALL_TEAMS
    assert result["rounds"] == SMALL_ROUNDS


# --- Roster sizing ----------------------------------------------------------


def test_roster_has_one_slot_per_round():
    """
    The bench was a fixed eight slots whatever the draft length, so a 20-round
    draft had two picks with nowhere to sit and a 15-round draft -- the setup
    form's default -- showed three bench rows nobody could ever fill.
    """
    for rounds in (12, 15, 18, 20):
        assert len(config.roster_slots(rounds)) == rounds

    assert config.roster_slots(15)[-1] == "BN5"


def test_a_draft_shorter_than_the_lineup_has_no_bench():
    slots = config.roster_slots(6)

    assert slots == config.DEFAULT_STARTERS
    assert not any(slot.startswith("BN") for slot in slots)


def test_every_pick_lands_in_a_slot(short_session):
    session_id, state = short_session
    _run_out_the_draft(session_id, state)

    user_team = state["teams_list"][0]
    filled = [player for player in user_team.roster.values() if player]

    assert len(filled) == user_team.picks_made == SMALL_ROUNDS


# --- VONA's span ------------------------------------------------------------


def _captured_span(monkeypatch, state, current_pick_num):
    """The picks_to_simulate _calculate_and_store_vona works out for a given pick."""
    seen = {}

    def fake_board(available, draft_obj, teams_list, picks_to_simulate, current_pick,
                   pick_owners=None):
        seen["picks"] = picks_to_simulate
        seen["owners"] = pick_owners
        return WaitingCost({}, {})

    monkeypatch.setattr(
        "backend.services.draft_manager_service.calculate_vona_board", fake_board
    )
    state["current_pick_num"] = current_pick_num
    DMS._calculate_and_store_vona(state)
    return seen.get("picks")


def test_vona_spans_to_the_next_turn_from_your_own_pick(monkeypatch, session):
    """On the clock, the span is what you give up by passing: picks 2..23."""
    _, state = session  # user picks at 1, 24, 25, 48

    assert _captured_span(monkeypatch, state, 0) == 23


def test_vona_has_a_span_off_your_turn_too(monkeypatch, session):
    """
    The point of the change: VONA used to exist only on the user's own pick.

    Off-turn the lookup could not find the pick on the clock in the user's list
    and gave up, leaving picks_to_simulate at 0 -- which calculate_vona_board
    reads as "waiting is free" and returns a board of exact zeroes for. The room
    had to grey the whole column out for every pick that was not yours.

    Sitting at pick 6 with your next turn at 24, eighteen picks stand between
    you and it, and those are exactly the ones that can take him.
    """
    _, state = session

    assert _captured_span(monkeypatch, state, 5) == 18


def test_vona_spans_back_to_back_picks(monkeypatch, session):
    """
    At the snake's turn, 24 and 25 are consecutive and the only pick in between
    is your own -- which you would spend on somebody else. One player leaves the
    pool, so the span is 1 rather than 0.
    """
    _, state = session

    assert _captured_span(monkeypatch, state, 23) == 1


def test_vona_has_no_span_after_your_last_pick(monkeypatch, session):
    """No turn left to wait for, so there is nothing waiting could cost."""
    _, state = session

    assert _captured_span(monkeypatch, state, 47) == 0


def test_state_carries_vona_off_your_turn(session):
    """
    End to end, against the real simulation: the board a CPU pick is showing has
    live VONA on it, not a column of zeroes.
    """
    session_id, state = session
    state["current_pick_num"] = 5  # a CPU pick; the user is next at 24

    players = DMS.get_current_draft_state(session_id)["available_players"]

    assert any(player["VONA"] > 0 for player in players)
    assert any(player["GONE"] > 0 for player in players)


# --- keepers and traded picks ------------------------------------------------
#
# The session-level half of the pick book. draft_order_test covers the book
# itself; these cover the service actually reading it, which is where the old
# snake arithmetic used to be and where a wrong answer means a player lands on
# somebody else's roster.

KEEPER_TEAMS = 4
KEEPER_ROUNDS = 3


def _keeper_session(trades=(), keepers=(), snake_from=2):
    """A small simulation session with a pick book, wired as initialize_draft does."""
    board = make_board()
    slots = config.roster_slots(KEEPER_ROUNDS)
    draft_obj = Draft(board.copy(), 'PPR', KEEPER_TEAMS, KEEPER_ROUNDS,
                      roster=slots, order='snake')
    teams_list = [Team(slots) for _ in range(KEEPER_TEAMS)]

    order = DraftOrder(KEEPER_TEAMS, KEEPER_ROUNDS, snake_from)
    book = keeper_files.LeagueBook(keepers=list(keepers), trades=list(trades))
    pick_book = keeper_files.build_pick_book(
        order, book, dict(zip(board['normalized_name'], board['display_name']))
    )
    DMS._seat_keepers(draft_obj, teams_list, pick_book)

    state = {
        "draft_obj": draft_obj,
        "teams_list": teams_list,
        "user_pick_slot": 1,
        "user_picks_simulation": pick_book.picks_for(0),
        "pick_book": pick_book,
        "draft_id": None,
        "non_interactive": True,
        "current_pick_num": pick_book.next_open_pick(0),
        "original_big_board": board.copy(),
        "picks_order": [],
        "slot_to_roster_id": {},
        "vona_data": {},
    }
    session_id = "test-keeper-session"
    DMS._active_draft_sessions[session_id] = state
    return session_id, state


@pytest.fixture
def keeper_session():
    session_id, state = _keeper_session(
        keepers=[{"player": "RB1", "round": 1, "pick": 1},
                 {"player": "WR1", "round": 1, "pick": 2}],
        trades=[{"round": 2, "pick": 3, "traded_to": 1}],
    )
    yield session_id, state
    DMS._active_draft_sessions.pop(session_id, None)


def test_the_draft_opens_past_its_keepers(keeper_session):
    """
    With the first two picks kept, the draft starts on pick three. Opening on a
    kept pick would sit there waiting for a pick nobody makes.
    """
    _, state = keeper_session
    assert state["current_pick_num"] == 2


def test_kept_players_are_off_the_board_from_the_start(keeper_session):
    """
    All of them at once, not each when its pick comes round -- everyone knows who
    was kept, so no valuation should ever have seen them available.
    """
    _, state = keeper_session
    available = set(state["draft_obj"].get_available_players()['normalized_name'])

    assert 'rb1' not in available
    assert 'wr1' not in available


def test_a_keeper_is_on_the_roster_that_kept_him(keeper_session):
    _, state = keeper_session

    assert 'rb1' in state["teams_list"][0].roster.values()
    assert 'wr1' in state["teams_list"][1].roster.values()
    assert state["teams_list"][0].picks_made == 1


def test_the_clock_follows_a_traded_pick(keeper_session):
    """Seat 3's round-two pick belongs to seat 1, and only the book knows that."""
    _, state = keeper_session
    order = state["pick_book"].order
    state["current_pick_num"] = order.pick_index(2, 3)

    assert DMS._team_on_clock(state) == 0


def test_a_cpu_pick_lands_on_the_team_that_owns_the_pick(keeper_session):
    """
    End to end through process_cpu_pick: the player has to join the roster of
    whoever holds the pick, not whoever sits in that seat.
    """
    session_id, state = keeper_session
    order = state["pick_book"].order
    state["current_pick_num"] = order.pick_index(2, 3)
    before = state["teams_list"][0].picks_made

    result = DMS.process_cpu_pick(session_id)

    assert "error" not in result
    assert state["teams_list"][0].picks_made == before + 1


def test_the_clock_steps_over_a_keeper_after_a_pick(keeper_session):
    """The skip has to happen on the way out of a pick, not only at startup."""
    session_id, state = keeper_session
    order = state["pick_book"].order

    # Keep the pick immediately after the one on the clock, then make that pick.
    state["pick_book"] = state["pick_book"].with_keepers([
        KeptPlayer("TE1", "te1", order.pick_index(1, 4), 3),
    ])
    state["current_pick_num"] = order.pick_index(1, 3)

    DMS.process_cpu_pick(session_id)

    # Seat 3 picks, seat 4's round-one pick is kept and drops out -- and because
    # round two reverses, the next live pick is seat 4's again at the turn.
    assert state["current_pick_num"] == order.pick_index(2, 4)


def test_the_vona_span_skips_kept_picks(monkeypatch, keeper_session):
    """
    A kept pick in the span is already made. Simulating it would take a player
    off the board who was never going to be taken, and overstate what waiting
    costs.
    """
    _, state = keeper_session
    order = state["pick_book"].order

    # Seat 4 keeps its round-two pick, which sits inside the span below.
    state["pick_book"] = state["pick_book"].with_keepers([
        KeptPlayer("TE1", "te1", order.pick_index(2, 4), 3),
    ])
    state["user_picks_simulation"] = state["pick_book"].picks_for(0)

    seen = {}

    def fake_board(available, draft_obj, teams_list, picks_to_simulate, current_pick,
                   pick_owners=None):
        seen["picks"] = picks_to_simulate
        seen["owners"] = pick_owners
        return WaitingCost({}, {})

    monkeypatch.setattr(
        "backend.services.draft_manager_service.calculate_vona_board", fake_board
    )
    state["current_pick_num"] = order.pick_index(1, 4)
    DMS._calculate_and_store_vona(state)

    # Between seat 4's round-one pick and the user's next turn lie exactly two
    # picks, and seat 4's round-two one is kept. So one pick gets simulated, not
    # two -- simulating the kept one would take a player off the board who was
    # never going anywhere and overstate what waiting costs.
    assert seen["picks"] == 1
    assert seen["owners"] == [3]
