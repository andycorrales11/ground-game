"""
Tests for resolving a FantasyPros player name to a Sleeper id.

These are pure functions over an in-memory index, so nothing here touches
nfl_data_py, Sleeper or the database. The identity rows below are the real shapes
that broke the board.
"""
import pytest

from backend.ingest.ingest_to_db import _build_name_index, _resolve_sleeper_id


# (name, position, sleeper_id) exactly as nfl.import_ids() returns them --
# note the ids arrive as floats, which is why "4881.0" has to become "4881".
NFLVERSE = [
    ("Lamar Jackson", "CB", 6994.0),        # Panthers corner
    ("Lamar Jackson", "QB", 4881.0),        # Ravens quarterback
    ("Justin Jefferson", "LB", 13524.0),    # 2026 Browns linebacker
    ("Justin Jefferson", "WR", 6794.0),     # Vikings receiver
    ("James Cook", "RB", 8138.0),           # FantasyPros writes "James Cook III"
    ("Patrick Mahomes", "QB", 4046.0),      # FantasyPros writes "Patrick Mahomes II"
    ("Travis Etienne", "RB", 7543.0),
    ("Kenneth Gainwell", "RB", 7567.0),     # FantasyPros writes "Kenny Gainwell"
    ("Jared Wiley", "TE", None),            # no Sleeper id at all
    ("Ghost Player", "WR", float("nan")),
]


@pytest.fixture
def index():
    names, positions, ids = zip(*NFLVERSE)
    return _build_name_index(names, positions, ids)


@pytest.mark.parametrize("name, pos, expected", [
    ("Lamar Jackson", "QB", "4881"),
    ("Lamar Jackson", "CB", "6994"),
    ("Justin Jefferson", "WR", "6794"),
    ("Justin Jefferson", "LB", "13524"),
])
def test_position_separates_players_who_share_a_name(index, name, pos, expected):
    """
    Two real players share each of these names.

    Resolving on the name alone is a coin flip, and losing it strips the ADP off a
    first-round player -- the board then shows them as N/A while a duplicate row
    carries their projection.
    """
    assert _resolve_sleeper_id(name, pos, index) == expected


def test_shared_name_without_a_position_is_not_guessed(index):
    assert _resolve_sleeper_id("Lamar Jackson", None, index) is None


def test_suffixes_are_bridged(index):
    """FantasyPros writes the suffix; nflverse usually does not."""
    assert _resolve_sleeper_id("James Cook III", "RB", index) == "8138"
    assert _resolve_sleeper_id("Patrick Mahomes II", "QB", index) == "4046"
    assert _resolve_sleeper_id("Travis Etienne Jr.", "RB", index) == "7543"


def test_name_map_handles_genuinely_different_spellings(index):
    """A nickname is not a suffix, so normalization cannot reach it."""
    assert _resolve_sleeper_id("Kenny Gainwell", "RB", index) == "7567"


def test_ids_are_stored_in_sleepers_own_form(index):
    """nfl_data_py hands back floats; a bare str() would yield '4881.0'."""
    resolved = _resolve_sleeper_id("Lamar Jackson", "QB", index)
    assert resolved == "4881"
    assert not resolved.endswith(".0")


def test_players_without_an_id_resolve_to_none(index):
    assert _resolve_sleeper_id("Jared Wiley", "TE", index) is None
    assert _resolve_sleeper_id("Ghost Player", "WR", index) is None


def test_unknown_players_resolve_to_none(index):
    assert _resolve_sleeper_id("Nobody At All", "WR", index) is None
    assert _resolve_sleeper_id(None, "WR", index) is None


def test_exact_match_beats_a_normalized_one():
    """
    A player whose exact name matches must never be pulled off it by normalization.

    "Chris Brazzell" and "Chris Brazzell II" normalize together, so the specific
    lookup has to win or the wrong id is returned for one of them.
    """
    index = _build_name_index(
        ["Chris Brazzell", "Chris Brazzell II"], ["WR", "WR"], [111.0, 222.0]
    )
    assert _resolve_sleeper_id("Chris Brazzell", "WR", index) == "111"
    assert _resolve_sleeper_id("Chris Brazzell II", "WR", index) == "222"


def test_position_mismatch_still_falls_back_to_the_name():
    """
    FantasyPros and nflverse sometimes disagree about position.

    An unambiguous name should still resolve rather than being thrown away over a
    positional disagreement.
    """
    index = _build_name_index(["Taysom Hill"], ["TE"], [3164.0])
    assert _resolve_sleeper_id("Taysom Hill", "QB", index) == "3164"
