"""
Bye weeks: parsing them out of either FantasyPros layout, recovering them from the
team, and reporting the weeks where a roster loses several players at once.
"""
import numpy as np
import pandas as pd
import pytest

from backend.ingest.ingest_to_db import (
    _canonicalize_teams,
    _fill_byes_from_team,
    _normalize_adp_frame,
)
from backend.services.draft import Draft, Team
from backend.services.draft_manager_service import _roster_and_conflicts


# --- parsing the two export layouts ------------------------------------------

def test_normalize_adp_frame_reads_the_bye_column_of_the_older_layout():
    df = pd.DataFrame({
        "Rank": [1, 2],
        "Player": ["Ja'Marr Chase", "Bijan Robinson"],
        "Team": ["CIN", "ATL"],
        "Bye": [10.0, 5.0],
        "POS": ["WR1", "RB1"],
        "AVG": [1.0, 3.0],
    })

    out = _normalize_adp_frame(df, "2025.csv")

    assert list(out["Bye"]) == [10.0, 5.0]


def test_normalize_adp_frame_extracts_the_bye_from_the_2026_player_cell():
    df = pd.DataFrame({
        "Player (Bye)": ["Jahmyr Gibbs   DET (6)", "Bijan Robinson   ATL (11)"],
        "POS": ["RB1", "RB2"],
        "AVG": [1.0, 2.0],
    })

    out = _normalize_adp_frame(df, "2026.csv")

    assert list(out["Player"]) == ["Jahmyr Gibbs", "Bijan Robinson"]
    assert list(out["Bye"]) == [6.0, 11.0]


def test_normalize_adp_frame_survives_an_older_layout_with_no_bye_column():
    """The bye is optional -- _fill_byes_from_team can recover it from the team."""
    df = pd.DataFrame({
        "Player": ["Ja'Marr Chase"],
        "Team": ["CIN"],
        "POS": ["WR1"],
        "AVG": [1.0],
    })

    out = _normalize_adp_frame(df, "no_bye.csv")

    assert "Bye" in out.columns
    assert out["Bye"].isna().all()


def test_unsigned_free_agents_keep_a_null_bye():
    """A bare name has no team, so there is no bye to infer."""
    df = pd.DataFrame({
        "Player (Bye)": ["Some Free Agent"],
        "POS": ["WR90"],
        "AVG": [400.0],
    })

    out = _normalize_adp_frame(df, "fa.csv")

    assert out["Player"].iloc[0] == "Some Free Agent"
    assert pd.isna(out["Team"].iloc[0])
    assert pd.isna(out["Bye"].iloc[0])


# --- recovering the bye from the team ----------------------------------------

def test_bye_is_filled_in_from_a_team_mate():
    """
    The projection-only deep pool arrives from Sleeper with a team but no ADP row,
    so their bye has to come off another player on the same team.
    """
    df = pd.DataFrame({
        "team": ["CIN", "CIN", "DET"],
        "bye": [10.0, np.nan, np.nan],
    })

    out = _fill_byes_from_team(df)

    assert out["bye"].iloc[1] == 10.0
    # Detroit has no dated player at all, so there is nothing to copy.
    assert pd.isna(out["bye"].iloc[2])


def test_one_bad_row_cannot_redate_a_whole_team():
    """The per-team value is the mode, not the first row."""
    df = pd.DataFrame({
        "team": ["CIN"] * 4,
        "bye": [99.0, 10.0, 10.0, np.nan],
    })

    out = _fill_byes_from_team(df)

    assert out["bye"].iloc[3] == 10.0


def test_a_player_with_no_team_keeps_a_null_bye():
    df = pd.DataFrame({"team": ["CIN", None], "bye": [10.0, np.nan]})

    out = _fill_byes_from_team(df)

    assert pd.isna(out["bye"].iloc[1])


def test_jacksonville_is_one_team_not_two():
    """
    FantasyPros writes JAC and Sleeper writes JAX. Left alone that splits the
    roster, which is what put 33 teams on a 32-team board.
    """
    df = pd.DataFrame({
        "team": ["JAC", "JAX", "CIN"],
        "bye": [7.0, np.nan, 10.0],
    })

    out = _fill_byes_from_team(_canonicalize_teams(df))

    assert set(out["team"]) == {"JAX", "CIN"}
    assert out["bye"].iloc[1] == 7.0


# --- Draft.player_bye ---------------------------------------------------------

def _board_with_byes():
    return pd.DataFrame({
        "display_name": ["Ja'Marr Chase", "Some Free Agent"],
        "normalized_name": ["jamarr_chase", "some_free_agent"],
        "pos": ["WR", "WR"],
        "team": ["CIN", None],
        "bye": [10.0, np.nan],
    })


def test_player_bye_returns_a_plain_int():
    draft = Draft(players=_board_with_byes())

    bye = draft.player_bye("jamarr_chase")

    assert bye == 10
    assert isinstance(bye, int)


def test_player_bye_is_none_for_a_null_bye():
    assert Draft(players=_board_with_byes()).player_bye("some_free_agent") is None


def test_player_bye_is_none_for_an_unknown_player():
    assert Draft(players=_board_with_byes()).player_bye("nobody") is None


def test_player_bye_is_none_on_a_board_with_no_bye_column():
    """The synthetic boards in the other tests predate the column."""
    board = _board_with_byes().drop(columns=["bye"])

    assert Draft(players=board).player_bye("jamarr_chase") is None


# --- Team bye tracking --------------------------------------------------------

def test_bye_conflicts_reports_weeks_with_two_or_more_players():
    team = Team(["QB1", "RB1", "RB2", "BN1"])
    team.add_player("qb", "QB", 7)
    team.add_player("rb_a", "RB", 7)
    team.add_player("rb_b", "RB", 10)

    assert team.bye_conflicts() == {7: ["qb", "rb_a"]}


def test_bye_conflicts_honours_a_higher_threshold():
    team = Team(["RB1", "RB2", "BN1"])
    for i, bye in enumerate([7, 7, 7]):
        team.add_player(f"p{i}", "RB", bye)

    assert team.bye_conflicts(threshold=3) == {7: ["p0", "p1", "p2"]}
    assert team.bye_conflicts(threshold=4) == {}


def test_players_with_an_unknown_bye_are_not_bucketed_together():
    """
    71 players in the pool are unsigned and have no bye. Grouping them would invent
    a week where the whole bench disappears.
    """
    team = Team(["BN1", "BN2", "BN3"])
    team.add_player("fa_a", "WR")
    team.add_player("fa_b", "WR")
    team.add_player("fa_c", "WR", None)

    assert team.bye_conflicts() == {}


def test_bye_week_reads_back_what_was_recorded():
    team = Team(["QB1"])
    team.add_player("qb", "QB", 9)

    assert team.bye_week("qb") == 9
    assert team.bye_week("never_drafted") is None


def test_copy_carries_the_bye_weeks():
    """The VONA simulation clones teams; a clone that forgot byes would misreport."""
    team = Team(["RB1", "RB2"])
    team.add_player("rb_a", "RB", 7)
    team.add_player("rb_b", "RB", 7)

    clone = team.copy()
    clone.add_player("rb_c", "RB", 7)

    assert team.bye_conflicts() == {7: ["rb_a", "rb_b"]}
    assert clone.bye_conflicts() == {7: ["rb_a", "rb_b", "rb_c"]}


def test_add_player_still_works_without_a_bye():
    """The CPU simulation does not carry the column and must not have to."""
    team = Team(["QB1", "QB2"])
    team.add_player("qb_a", "QB")
    team.add_player("qb_b", "QB")

    assert team.count_players_at_position("QB") == 2
    assert team.bye_conflicts() == {}


# --- what the API actually returns --------------------------------------------

def _roster_board():
    return pd.DataFrame({
        "display_name": ["Chris Olave", "Christian McCaffrey"],
        "normalized_name": ["chris_olave", "christian_mccaffrey"],
        "pos": ["WR", "RB"],
        "bye": [8.0, 8.0],
    })


def test_roster_and_conflicts_agree_on_what_a_player_is_called():
    """
    Team.roster holds normalized names. The warning used to report those while the
    roster table beside it reported display names, so the same player appeared under
    two spellings on one screen.
    """
    team = Team(["RB1", "WR1", "BN1"])
    team.add_player("christian_mccaffrey", "RB", 8)
    team.add_player("chris_olave", "WR", 8)

    rows, conflicts = _roster_and_conflicts(team, _roster_board())

    assert conflicts == {8: ["Chris Olave", "Christian McCaffrey"]}
    assert [r["player"] for r in rows] == ["Christian McCaffrey", "Chris Olave", None]
    assert [r["bye"] for r in rows] == [8, 8, None]
    assert [r["pos"] for r in rows] == ["RB", "WR", None]


def test_roster_view_falls_back_to_the_stored_name_when_the_board_lacks_it():
    team = Team(["RB1"])
    team.add_player("someone_unlisted", "RB", 5)

    rows, conflicts = _roster_and_conflicts(team, _roster_board())

    assert rows[0]["player"] == "someone_unlisted"
    assert conflicts == {}


def test_roster_view_tolerates_an_empty_board():
    team = Team(["RB1"])
    team.add_player("christian_mccaffrey", "RB", 8)

    rows, _ = _roster_and_conflicts(team, pd.DataFrame())

    assert rows[0]["player"] == "christian_mccaffrey"
    assert rows[0]["bye"] == 8
