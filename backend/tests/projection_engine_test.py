"""
Parity, property, and sensitivity tests for the projection engine.

The parity test is the one that matters. The workbook computed these numbers in
Excel; the engine computes them in Python from the same inputs. Agreement to
1e-9 across 447 players and 12 stat categories is not a tolerance that a
transcription error survives -- a share denominator spanning the wrong rows, or
touchdowns taken per attempt instead of per completion, misses by percent, not
by 1e-9.

So the tolerance stays tight. If this test starts failing, do not widen it.
"""
import csv
from pathlib import Path

import pytest

from backend.league import ScoringSettings
from backend.services.projection_engine import (
    PlayerRates,
    ProjectionInputs,
    TeamVolume,
    UNLISTED_LEAKAGE,
    project_all,
    project_team,
    score,
)

FIXTURES = Path(__file__).parent / 'fixtures'

# Excel's own arithmetic is what produced the expected values, so the only error
# in play is double-precision rounding across a handful of multiplications.
TOLERANCE = 1e-9

STAT_FIELDS = (
    'pass_attempts', 'completions', 'pass_yards', 'pass_tds', 'interceptions',
    'rush_attempts', 'rush_yards', 'rush_tds',
    'targets', 'receptions', 'recv_yards', 'recv_tds',
)

# Five cells in the whole workbook hold literal numbers where every other tab
# holds a formula. Both clusters are workbook defects, and the engine -- which
# reads inputs and recomputes by design -- disagrees with both:
#
#   ARI!G4     hardcoded 0, overwriting `=E4*T4` (spec §9, item 2). Carson Beck's
#              rates still say ~2.9 passing touchdowns, so that is what the
#              engine produces. This one does change his score.
#
#   NO!L3:O3   a receiving line -- 32.2 targets, 23.7 catches, 258.7 yards, 2.4
#              touchdowns -- pasted onto a quarterback's row, with no share
#              weight or rate behind it to derive it from. Not in spec §9; the
#              audit there looked for broken formulas, and these are cells that
#              should hold nothing at all. They are inert: the QB scoring formula
#              has no reception terms, so nothing downstream reads them, which is
#              why `custom_points` still matches for Rattler.
#
# Recorded as documented exceptions rather than fixed by widening the tolerance,
# because those are very different claims: one says "the workbook has five broken
# cells", the other says "the engine is approximately right everywhere". Only the
# first is true.
HARDCODED_OVERRIDES = {
    ('ARI', 4): ('pass_tds', 'custom_points'),
    ('NO', 3): ('targets', 'receptions', 'recv_yards', 'recv_tds'),
}


def _rows(name: str) -> list[dict]:
    with (FIXTURES / name).open(newline='', encoding='utf-8') as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope='module')
def inputs() -> ProjectionInputs:
    volumes = {
        row['team']: TeamVolume.from_record(row)
        for row in _rows('workbook_inputs_teams.csv')
    }
    players = [PlayerRates.from_record(row) for row in _rows('workbook_inputs_players.csv')]
    return ProjectionInputs(volumes=volumes, players=players)


@pytest.fixture(scope='module')
def expected() -> dict[tuple[str, int], dict]:
    return {(row['team'], int(row['row'])): row for row in _rows('workbook_parity.csv')}


@pytest.fixture(scope='module')
def projected(inputs) -> dict[tuple[str, int], object]:
    # Half-PPR with the workbook's own scoring values, which is the state its
    # cached `Custom` column was computed in.
    return {(p.team, p.key): p for p in project_all(inputs, ScoringSettings())}


def test_fixture_covers_every_scored_player(expected, projected):
    """The parity fixture is the workbook's 447 scored players, no more, no less."""
    assert len(expected) == 447
    assert set(expected) <= set(projected)


def test_engine_reproduces_workbook_stat_lines(expected, projected):
    """Every projected stat, for every scored player, to 1e-9."""
    mismatches = []

    for key, row in expected.items():
        player = projected[key]
        skip = HARDCODED_OVERRIDES.get(key, ())

        for stat in STAT_FIELDS:
            if stat in skip:
                continue
            actual = getattr(player.line, stat)
            want = float(row[stat])
            if abs(actual - want) > TOLERANCE:
                mismatches.append(
                    f"{row['team']}!{row['row']} {row['name']} {stat}: "
                    f"got {actual!r}, workbook has {want!r}"
                )

    assert not mismatches, "\n".join(mismatches[:20])


def test_engine_reproduces_workbook_custom_points(expected, projected):
    """The scoring dot product, against the workbook's `Custom` column."""
    mismatches = []

    for key, row in expected.items():
        if 'custom_points' in HARDCODED_OVERRIDES.get(key, ()):
            continue
        actual = projected[key].points
        want = float(row['custom_points'])
        if abs(actual - want) > TOLERANCE:
            mismatches.append(
                f"{row['team']}!{row['row']} {row['name']}: "
                f"got {actual!r}, workbook has {want!r}"
            )

    assert not mismatches, "\n".join(mismatches[:20])


def test_documented_divergences_are_workbook_defects(expected, projected):
    """
    Both exceptions are real, and both are the workbook's rather than the
    engine's.

    Asserting the *shape* of each divergence keeps the exception list honest: if
    the workbook is ever fixed, or the engine drifts, this fails and the list
    gets revisited instead of quietly covering something new.
    """
    # A passing touchdown cell overwritten with a zero.
    beck = projected[('ARI', 4)]
    assert beck.name == 'Carson Beck'
    assert float(expected[('ARI', 4)]['pass_tds']) == 0.0
    assert beck.line.pass_tds == pytest.approx(2.94, abs=0.05)

    # A receiving line pasted onto a quarterback, with nothing behind it.
    rattler = projected[('NO', 3)]
    assert rattler.name == 'Spencer Rattler' and rattler.pos == 'QB'
    assert float(expected[('NO', 3)]['receptions']) > 20
    assert rattler.line.receptions == 0.0

    # Inert, though: quarterbacks are not scored on receptions, so the workbook's
    # own total for him is the one the engine reproduces exactly.
    assert rattler.points == pytest.approx(
        float(expected[('NO', 3)]['custom_points']), abs=TOLERANCE
    )


# --- Properties that hold whatever the inputs are -----------------------------

def test_shares_sum_to_their_expected_totals(inputs):
    """
    Pass share sums to 1.0; rush and target share sum to 0.98.

    The 2% is deliberate leakage for players nobody lists. Pass share is not
    scaled because every attempt has to be thrown by a listed quarterback -- and
    that asymmetry is exactly the kind of thing a rewrite flattens by accident.
    """
    for volume, players in inputs.by_team():
        lines = project_team(volume, players)

        thrown = sum(lines[p.key].pass_attempts for p in players)
        carried = sum(lines[p.key].rush_attempts for p in players)
        targeted = sum(lines[p.key].targets for p in players)

        assert thrown == pytest.approx(volume.pass_attempts, rel=1e-9)
        assert carried == pytest.approx(volume.rush_attempts * UNLISTED_LEAKAGE, rel=1e-9)
        assert targeted == pytest.approx(thrown * UNLISTED_LEAKAGE, rel=1e-9)


def test_no_position_produces_stats_it_cannot(inputs):
    """Tight ends do not run, quarterbacks do not catch."""
    for player in project_all(inputs, ScoringSettings()):
        if player.pos == 'TE':
            assert player.line.rush_attempts == 0.0
        if player.pos == 'QB':
            assert player.line.receptions == 0.0
        if player.pos != 'QB':
            assert player.line.pass_attempts == 0.0


def test_bumping_one_target_share_dilutes_teammates(inputs):
    """
    Shares are relative weights, not percentages.

    This is the behaviour the whole normalization step exists for: you cannot
    give a receiver more of the offence without taking it from someone.
    """
    volume = inputs.volumes['ARI']
    players = [p for p in inputs.players if p.team == 'ARI']
    before = project_team(volume, players)

    bumped = [
        PlayerRates(**{**p.__dict__, 'w_tgt': p.w_tgt * 2}) if p.name == 'Trey McBride' else p
        for p in players
    ]
    after = project_team(volume, bumped)

    mcbride = next(p for p in players if p.name == 'Trey McBride')
    teammates = [p for p in players if p.pos in ('RB', 'WR', 'TE') and p.key != mcbride.key]

    assert after[mcbride.key].targets > before[mcbride.key].targets
    assert all(after[p.key].targets < before[p.key].targets for p in teammates if p.w_tgt > 0)


# --- Sensitivity to league settings -------------------------------------------

def test_ppr_lifts_pass_catchers_and_standard_does_not(inputs):
    """
    The knob the old three-column schema could express, still working.

    A running back who catches 70 passes gains 70 points going from standard to
    full PPR; one who catches none gains nothing.
    """
    standard = {
        (p.team, p.key): p for p in project_all(inputs, ScoringSettings.for_format('STD'))
    }
    ppr = {(p.team, p.key): p for p in project_all(inputs, ScoringSettings.for_format('PPR'))}

    for key, player in ppr.items():
        gain = player.points - standard[key].points
        assert gain == pytest.approx(player.line.receptions, rel=1e-9)


def test_scoring_values_the_old_schema_could_not_express(inputs):
    """
    Six-point passing touchdowns, and a tight-end premium.

    Neither is expressible as one of three precomputed columns, which is the
    entire reason the engine exists.
    """
    base = ScoringSettings.for_format('HalfPPR')
    six_point = base.with_overrides({'pass_tds': 6.0})

    quarterbacks = {
        (p.team, p.key): p for p in project_all(inputs, base) if p.pos == 'QB'
    }
    boosted = {
        (p.team, p.key): p for p in project_all(inputs, six_point) if p.pos == 'QB'
    }
    for key, player in boosted.items():
        gain = player.points - quarterbacks[key].points
        assert gain == pytest.approx(quarterbacks[key].line.pass_tds * 2, rel=1e-9)

    premium = base.with_overrides({'receptions_te': 1.5})
    tight_ends = {(p.team, p.key): p for p in project_all(inputs, base) if p.pos == 'TE'}
    lifted = {(p.team, p.key): p for p in project_all(inputs, premium) if p.pos == 'TE'}
    for key, player in lifted.items():
        gain = player.points - tight_ends[key].points
        assert gain == pytest.approx(tight_ends[key].line.receptions * 1.0, rel=1e-9)

    # And the premium is genuinely per position: nobody else moved.
    assert all(
        p.points == pytest.approx(q.points, rel=1e-12)
        for p, q in zip(
            [p for p in project_all(inputs, premium) if p.pos == 'WR'],
            [p for p in project_all(inputs, base) if p.pos == 'WR'],
        )
    )


def test_unknown_scoring_setting_is_rejected():
    """
    A typo in an override scores the whole league wrong, silently, forever.

    So it raises. The caller is our own API payload, not user free-text.
    """
    with pytest.raises(ValueError, match='ppr_bonus'):
        ScoringSettings().with_overrides({'ppr_bonus': 1.0})


def test_score_of_an_empty_line_is_zero():
    from backend.services.projection_engine import StatLine

    assert score(StatLine(), 'WR', ScoringSettings.for_format('PPR')) == 0.0


def test_team_with_no_share_weights_projects_zero_rather_than_dividing_by_zero():
    volume = TeamVolume(team='XXX', plays=1000.0, pass_pct=0.6, rush_ypc=4.2)
    players = [PlayerRates(team='XXX', key=1, name='Nobody', pos='RB')]

    lines = project_team(volume, players)

    assert lines[1].rush_attempts == 0.0
    assert lines[1].targets == 0.0
