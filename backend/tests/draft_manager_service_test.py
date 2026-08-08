"""
Tests for DraftManagerService, driven off a synthetic session so they need no
database and no running Sleeper draft.

process_auto_pick_helper is the one method on this service that is not a passthrough
to its simulation counterpart, and it is the live room's "pick for me" button.
"""
import numpy as np
import pytest

from backend.services.draft import Draft, Team
from backend.services.draft_manager_service import DraftManagerService as DMS
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
