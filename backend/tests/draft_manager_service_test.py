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
from backend.services.draft_service import get_user_picks
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
    state = {
        "draft_obj": draft_obj,
        "teams_list": [Team() for _ in range(TEAMS)],
        "user_pick_slot": 1,
        "user_picks_simulation": [1, 24, 25, 48],
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
    state = {
        "draft_obj": draft_obj,
        "teams_list": [Team(slots) for _ in range(SMALL_TEAMS)],
        "user_pick_slot": 1,
        "user_picks_simulation": get_user_picks(1, 'snake', SMALL_TEAMS, SMALL_ROUNDS),
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
