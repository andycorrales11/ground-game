"""
Tests for league configuration: scoring presets, roster shape, replacement level.

The theme running through these is backward compatibility. Roster shape used to
be a module-level constant and scoring used to be one of three strings, so the
first thing to prove is that a league which says nothing about either still
drafts exactly as it did -- and only then that the new knobs do anything.
"""
import pytest

from backend import config
from backend.league import (
    RosterSettings,
    ScoringSettings,
    position_slots_from,
    replacement_rank,
)
from backend.services.draft import Team


# --- Defaults must not move ---------------------------------------------------

def test_default_roster_reproduces_the_module_constant():
    """
    The default lineup is the one the app has always used.

    If this fails, every existing draft just changed shape.
    """
    assert RosterSettings().starting_slots() == config.DEFAULT_STARTERS
    assert RosterSettings().position_slots() == config.DEFAULT_ROSTER_POS


def test_default_replacement_levels_match_the_old_arithmetic():
    """
    The old rule was `starters * teams + int(flex * teams * 0.5)` for RB and WR,
    and `starters * teams` for everything else. Charging flex demand fractionally
    is a generalization of that, not a change to it.
    """
    roster = RosterSettings(teams=12)

    assert roster.replacement_rank('RB') == 2 * 12 + int(2 * 12 * 0.5)
    assert roster.replacement_rank('WR') == 2 * 12 + int(2 * 12 * 0.5)
    assert roster.replacement_rank('TE') == 1 * 12
    assert roster.replacement_rank('QB') == 1 * 12
    assert roster.replacement_rank('K') == 1 * 12


def test_bench_is_sized_from_the_draft_length():
    for rounds in range(10, 26):
        assert len(RosterSettings().slots(rounds)) == rounds

    assert RosterSettings().slots(15)[-1] == 'BN5'
    # A draft shorter than the lineup gets no bench at all, and keeps the whole
    # starting lineup with slots that simply never get filled -- which is what
    # actually happens in such a league.
    assert RosterSettings().slots(6) == config.DEFAULT_STARTERS


def test_scoring_presets_differ_only_in_receptions():
    std = ScoringSettings.for_format('STD')
    half = ScoringSettings.for_format('HalfPPR')
    ppr = ScoringSettings.for_format('PPR')

    assert (std.receptions_rb, half.receptions_rb, ppr.receptions_rb) == (0.0, 0.5, 1.0)

    for settings in (half, ppr):
        for name, value in std.to_dict().items():
            if name.startswith('receptions_'):
                continue
            assert getattr(settings, name) == value, name


def test_half_ppr_spelling_survives_every_alias():
    """
    'HalfPPR'.lower() is 'halfppr', not the 'half_ppr' the columns use. That gap
    used to make half-PPR raise a KeyError on every draft, so the alias handling
    is worth pinning down here too.
    """
    for spelling in ('HalfPPR', 'half_ppr', 'HALF_PPR', 'Half PPR', 'half'):
        assert ScoringSettings.for_format(spelling).receptions_wr == 0.5


# --- The new knobs ------------------------------------------------------------

def test_superflex_adds_a_slot_and_moves_quarterback_replacement_level():
    """
    The whole reason superflex plays differently: a second startable quarterback
    per team doubles how deep the league goes at the position.
    """
    standard = RosterSettings(teams=12)
    superflex = RosterSettings(teams=12, superflex=1)

    assert 'SFLEX1' in superflex.starting_slots()
    assert standard.replacement_rank('QB') == 12
    assert superflex.replacement_rank('QB') == 24

    # And it does not disturb anyone else.
    for position in ('RB', 'WR', 'TE'):
        assert superflex.replacement_rank(position) == standard.replacement_rank(position)


def test_a_superflex_slot_takes_a_quarterback_and_a_plain_flex_does_not():
    roster = RosterSettings(teams=12, superflex=1).slots(20)

    team = Team(roster)
    team.add_player('first_qb', 'QB')
    team.add_player('second_qb', 'QB')

    assert team.roster['QB1'] == 'first_qb'
    assert team.roster['SFLEX1'] == 'second_qb'

    # A running back still prefers the plain flex, so it is not sitting on the
    # only slot the next quarterback could have used.
    plain = Team(RosterSettings(teams=12, superflex=1).slots(20))
    plain.add_player('rb1', 'RB')
    plain.add_player('rb2', 'RB')
    plain.add_player('rb3', 'RB')

    assert plain.roster['FLEX1'] == 'rb3'
    assert plain.roster['SFLEX1'] is None


def test_roster_counts_shape_the_lineup():
    roster = RosterSettings(teams=10, qb=1, rb=2, wr=3, te=1, flex=1, k=0, dst=0)

    assert roster.starting_slots() == [
        'QB1', 'RB1', 'RB2', 'WR1', 'WR2', 'WR3', 'TE1', 'FLEX1',
    ]
    assert roster.replacement_rank('WR') == 10 * 3 + int(10 * 1 * 0.5)


def test_position_slots_are_recovered_from_slot_names():
    """
    The VONA simulation only has the Draft's slot names to go on, so it has to be
    able to get back to the lineup from them -- otherwise a superflex draft
    values quarterbacks correctly on the board and then simulates opponents who
    do not.
    """
    roster = RosterSettings(teams=12, superflex=1)
    recovered = position_slots_from(roster.slots(20))

    assert recovered == roster.position_slots()
    assert 'BN' not in recovered
    assert replacement_rank('QB', 12, recovered) == 24


# --- Rejecting nonsense -------------------------------------------------------

def test_unknown_settings_are_rejected_rather_than_ignored():
    with pytest.raises(ValueError, match='half_point_ppr'):
        ScoringSettings().with_overrides({'half_point_ppr': 0.5})

    with pytest.raises(ValueError, match='kicker'):
        RosterSettings.from_payload(roster={'kicker': 1})


def test_an_empty_or_impossible_roster_is_rejected():
    with pytest.raises(ValueError):
        RosterSettings(teams=0)

    with pytest.raises(ValueError):
        RosterSettings(rb=-1)

    with pytest.raises(ValueError, match='at least one starting slot'):
        RosterSettings(qb=0, rb=0, wr=0, te=0, flex=0, superflex=0, k=0, dst=0)


def test_payload_defaults_match_the_no_argument_settings():
    assert RosterSettings.from_payload() == RosterSettings()
    assert RosterSettings.from_payload(teams=14).teams == 14
    assert RosterSettings.from_payload(teams=14, roster={'WR': 3}).wr == 3
