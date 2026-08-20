"""
Tests for the keeper and trade files.

The theme is that this module refuses rather than copes. Everything it reads is
hand-written off a draft sheet, and every mistake available produces a draft that
runs perfectly while belonging to the wrong people -- a keeper that quietly fails
to apply leaves the player on the board *and* leaves his pick live, which is two
compounding errors that nothing downstream can detect.

So: an unresolved name refuses to start, a keeper whose stated manager disagrees
with the pick's owner refuses to start, and a duplicate refuses to start.
"""
import json

import pytest

from backend import keepers as keeper_files
from backend.draft_order import DraftOrder


BOARD = {
    "jahmyr_gibbs": "Jahmyr Gibbs",
    "caleb_williams": "Caleb Williams",
    "emeka_egbuka": "Emeka Egbuka",
    "bijan_robinson": "Bijan Robinson",
}


@pytest.fixture
def order():
    return DraftOrder(teams=12, rounds=15, snake_from=4)


def write(tmp_path, keepers=None, trades=None):
    if keepers is not None:
        (tmp_path / keeper_files.KEEPERS_FILE).write_text(
            json.dumps(keepers), encoding="utf-8"
        )
    if trades is not None:
        (tmp_path / keeper_files.TRADES_FILE).write_text(
            json.dumps(trades), encoding="utf-8"
        )
    return tmp_path


# --- loading -----------------------------------------------------------------

def test_no_files_is_not_an_error(tmp_path):
    """A league without keepers is the normal case, and every mock draft is one."""
    book = keeper_files.load(tmp_path)

    assert not book
    assert book.keepers == [] and book.trades == []


def test_trades_may_be_a_bare_list_or_carry_its_managers(tmp_path):
    write(tmp_path, trades=[{"round": 2, "pick": 3, "traded_to": 5}])
    assert keeper_files.load(tmp_path).trades == [
        {"round": 2, "pick": 3, "traded_to": 5}
    ]

    write(tmp_path, trades={"managers": {"Andy": 9}, "trades": []})
    assert keeper_files.load(tmp_path).managers == {"Andy": 9}


def test_malformed_json_names_the_file(tmp_path):
    (tmp_path / keeper_files.KEEPERS_FILE).write_text("[{oops}]", encoding="utf-8")
    with pytest.raises(ValueError, match="keepers.json is not valid JSON"):
        keeper_files.load(tmp_path)


# --- resolving ---------------------------------------------------------------

def test_a_keeper_takes_the_pick_at_his_round_and_seat(tmp_path, order):
    write(tmp_path, keepers=[{"player": "Jahmyr Gibbs", "round": 1, "pick": 10}])

    picks = keeper_files.build_pick_book(order, keeper_files.load(tmp_path), BOARD)
    keeper = picks.keepers()[0]

    assert keeper.pick_index == order.pick_index(1, 10)
    assert keeper.team_index == 9
    assert 10 not in picks.picks_for(9)


def test_the_board_spelling_wins(tmp_path, order):
    """
    The sheet says what the manager calls him; the board says what the rest of the
    app calls him. Everything downstream matches on the normalized name, so the
    display name has to be the board's or the roster panel disagrees with itself.
    """
    write(tmp_path, keepers=[{"player": "jahmyr gibbs", "round": 1, "pick": 10}])

    picks = keeper_files.build_pick_book(order, keeper_files.load(tmp_path), BOARD)
    assert picks.keepers()[0].player == "Jahmyr Gibbs"


def test_a_keeper_follows_the_pick_that_was_traded(tmp_path, order):
    """
    The composition that makes the two files worth having separately, and the case
    straight off the sheet: Caleb Williams is written in Adrian's round-5 row, but
    that pick belongs to Andy, so Andy keeps him.
    """
    write(
        tmp_path,
        keepers=[{"player": "Caleb Williams", "round": 5, "pick": 10}],
        trades={
            "managers": {"Andy": 9, "Adrian": 10},
            "trades": [{"round": 5, "pick": 10, "traded_to": "Andy"}],
        },
    )

    picks = keeper_files.build_pick_book(order, keeper_files.load(tmp_path), BOARD)
    keeper = picks.keepers()[0]

    assert keeper.team_index == 8      # Andy, slot 9
    assert keeper.manager == "Andy"


def test_an_unresolved_keeper_refuses_to_start(tmp_path, order):
    """
    Named, and with the pick it was on, because the fix is a spelling change and
    you need to know which row to look at.
    """
    write(tmp_path, keepers=[{"player": "Nobody At All", "round": 2, "pick": 4}])

    with pytest.raises(ValueError, match=r"R2 P4 Nobody At All"):
        keeper_files.build_pick_book(order, keeper_files.load(tmp_path), BOARD)


def test_a_stated_manager_that_disagrees_with_the_pick_refuses_to_start(tmp_path, order):
    """
    The cross-check that earns its keep. The sheet already knows who ends up with
    the player, so a mismatch means either the keeper's row or the trade on that
    pick is wrong -- and both produce a valid-looking draft otherwise.
    """
    write(
        tmp_path,
        keepers=[{"player": "Caleb Williams", "round": 5, "pick": 10,
                  "manager": "Andy"}],
        trades={"managers": {"Andy": 9, "Adrian": 10}, "trades": []},
    )

    with pytest.raises(ValueError, match="the file says Andy keeps him"):
        keeper_files.build_pick_book(order, keeper_files.load(tmp_path), BOARD)


def test_a_matching_stated_manager_is_accepted(tmp_path, order):
    write(
        tmp_path,
        keepers=[{"player": "Jahmyr Gibbs", "round": 1, "pick": 10,
                  "manager": "Adrian"}],
        trades={"managers": {"Andy": 9, "Adrian": 10}, "trades": []},
    )

    picks = keeper_files.build_pick_book(order, keeper_files.load(tmp_path), BOARD)
    assert picks.keepers()[0].manager == "Adrian"


def test_the_same_player_kept_twice_refuses_to_start(tmp_path, order):
    write(tmp_path, keepers=[
        {"player": "Bijan Robinson", "round": 1, "pick": 8},
        {"player": "Bijan Robinson", "round": 4, "pick": 2},
    ])

    with pytest.raises(ValueError, match="kept more than once"):
        keeper_files.build_pick_book(order, keeper_files.load(tmp_path), BOARD)


def test_a_missing_field_names_the_entry(tmp_path, order):
    write(tmp_path, keepers=[{"player": "Jahmyr Gibbs", "round": 1}])

    with pytest.raises(ValueError, match="missing 'pick'"):
        keeper_files.build_pick_book(order, keeper_files.load(tmp_path), BOARD)


def test_without_a_board_names_are_taken_as_written(tmp_path, order):
    """
    `board_names=None` is for callers that have no board yet -- the converter and
    its tests. Resolution is the draft's job, not the file's.
    """
    write(tmp_path, keepers=[{"player": "Somebody New", "round": 1, "pick": 1}])

    picks = keeper_files.build_pick_book(order, keeper_files.load(tmp_path))
    assert picks.keepers()[0].player == "Somebody New"
