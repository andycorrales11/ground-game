"""
League configuration: what a point is worth, and what a starting lineup looks like.

Both used to be implicit. Scoring was a *format string* -- 'STD' | 'PPR' |
'HalfPPR' -- which selected one of three precomputed columns in the database, so
a league that paid 6 points for a passing touchdown had nowhere to say so. The
lineup was `config.DEFAULT_STARTERS`, a module-level constant, so every league
started the same ten players.

The projection engine changes the first of those: points are computed from rate
inputs at draft time, against whatever values the league actually uses. This
module is what carries those values from the API into the engine and into VORP.

The format string does not go away -- ADP is still a per-format column in the
database, and there is no way to derive "where the field drafts this player"
from a scoring table. So a session carries both: a format, which picks the ADP
column and seeds the scoring defaults, and a ScoringSettings, which is what
actually scores the projections.
"""
from dataclasses import dataclass, fields, replace
from typing import Any, Dict, List, Mapping

from backend import utils


@dataclass(frozen=True)
class ScoringSettings:
    """
    Points per unit of production.

    Field names and defaults are the workbook's `TableLeagueSettings` (spec
    §2.1), which is a standard scoring table apart from one thing worth noting:
    receptions are valued **per position**. A league can pay a tight end 1.0 per
    catch and a running back 0.5, and this is the only place in the codebase that
    can express that -- the three ADP columns cannot.

    Defaults are half-PPR, matching the workbook's shipped state. Use
    `for_format` to get the STD or PPR variant.
    """

    pass_attempts: float = 0.0
    completions: float = 0.0
    pass_yards: float = 0.04
    pass_tds: float = 4.0
    interceptions: float = -2.0

    rush_attempts: float = 0.0
    rush_yards: float = 0.1
    rush_tds: float = 6.0

    targets: float = 0.0
    receptions_rb: float = 0.5
    receptions_wr: float = 0.5
    receptions_te: float = 0.5
    recv_yards: float = 0.1
    recv_tds: float = 6.0

    def receptions_for(self, pos: str) -> float:
        """
        The per-catch value for a position.

        Quarterbacks never catch passes in this model, so anything that is not a
        pass-catching position scores 0 per reception rather than raising -- the
        master tables simply have no reception column for QB.
        """
        return {
            'RB': self.receptions_rb,
            'WR': self.receptions_wr,
            'TE': self.receptions_te,
        }.get(pos, 0.0)

    @classmethod
    def for_format(cls, scoring_format: str | None) -> "ScoringSettings":
        """
        The preset for a scoring format.

        The three formats differ *only* in what a reception is worth. Everything
        else -- passing, rushing, yardage, touchdowns -- is identical across
        them, which is exactly why a format string was never enough to describe
        a real league.
        """
        per_catch = {'STD': 0.0, 'HalfPPR': 0.5, 'PPR': 1.0}[
            utils.normalize_scoring_format(scoring_format)
        ]
        return cls(
            receptions_rb=per_catch,
            receptions_wr=per_catch,
            receptions_te=per_catch,
        )

    def with_overrides(self, overrides: Mapping[str, Any] | None) -> "ScoringSettings":
        """
        A copy with the named values replaced.

        Unknown keys raise rather than being dropped. A typo in a scoring
        override is the kind of thing that would otherwise silently score the
        whole league wrong, and the caller is an API payload we control.
        """
        if not overrides:
            return self

        known = {f.name for f in fields(self)}
        unknown = set(overrides) - known
        if unknown:
            raise ValueError(
                f"Unknown scoring setting(s): {', '.join(sorted(unknown))}. "
                f"Valid settings: {', '.join(sorted(known))}."
            )
        return replace(self, **{k: float(v) for k, v in overrides.items()})

    def to_dict(self) -> Dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


# How a flex slot's demand is charged to each position when finding replacement
# level. The RB/WR split was hardcoded at 50/50 inside calculate_vorp; it is a
# tuning constant, not a derivation, so it lives here where it can be seen.
# Tight ends are flex-eligible but are so rarely started there that charging
# them any of it would move TE replacement level for no reason.
FLEX_SHARE: Dict[str, float] = {'RB': 0.5, 'WR': 0.5}

# A superflex slot is a quarterback slot in all but name. Leagues that run one
# see QB2s drafted like RB1s, which is the entire point of the format, so the
# whole slot is charged to QB.
SUPERFLEX_SHARE: Dict[str, float] = {'QB': 1.0}


def position_slots_from(slots: List[str]) -> List[str]:
    """
    The starting lineup, as bare positions, recovered from a list of slot names.

    A `Draft` carries its slot names but not the settings they came from, and the
    forward simulation inside VONA needs replacement levels that match the league
    it is simulating -- otherwise a superflex draft values quarterbacks correctly
    on the board and then simulates opponents who do not.
    """
    return [
        slot.rstrip('0123456789')
        for slot in slots
        if not slot.startswith('BN')
    ]


def replacement_rank(position: str, teams: int, position_slots: List[str]) -> int:
    """
    How many players at `position` the league starts -- the rank whose projection
    replacement level is read from.

    Flex demand is charged fractionally rather than to one position: with two
    flexes in a 12-team league, 36 running backs get started, not 24, and it is
    the 37th that a team can pick up off waivers for nothing.

    `position_slots` is the starting lineup as bare positions, with 'FLEX' and
    'SFLEX' left in as themselves. Passing the list rather than a RosterSettings
    keeps `calculate_vorp` callable with a hand-written lineup, which is how its
    tests pin the arithmetic down.
    """
    starters = position_slots.count(position)
    flex = position_slots.count('FLEX')
    superflex = position_slots.count('SFLEX')

    demand = (
        starters
        + flex * FLEX_SHARE.get(position, 0.0)
        + superflex * SUPERFLEX_SHARE.get(position, 0.0)
    )
    return int(teams * demand)


@dataclass(frozen=True)
class RosterSettings:
    """
    The starting lineup, as counts rather than slot names.

    Defaults reproduce `config.DEFAULT_STARTERS` exactly -- 1QB/2RB/2WR/1TE with
    two flexes, a kicker and a defense -- so a session that says nothing about
    its roster drafts precisely as it did before this existed.

    `superflex` is the one genuinely new capability. It costs nothing on the
    scoring side now that points are computed rather than column-selected, but
    it does move QB replacement level a long way (see SUPERFLEX_SHARE), which is
    the whole reason the format plays differently.
    """

    teams: int = 12
    qb: int = 1
    rb: int = 2
    wr: int = 2
    te: int = 1
    flex: int = 2
    superflex: int = 0
    k: int = 1
    dst: int = 1

    # Slot name stem per field, in the order they appear on a lineup card.
    _SLOT_ORDER = (
        ('qb', 'QB'), ('rb', 'RB'), ('wr', 'WR'), ('te', 'TE'),
        ('flex', 'FLEX'), ('superflex', 'SFLEX'), ('k', 'K'), ('dst', 'DEF'),
    )

    def __post_init__(self):
        if self.teams < 1:
            raise ValueError(f"A league needs at least one team, got {self.teams}.")
        for name, _ in self._SLOT_ORDER:
            if getattr(self, name) < 0:
                raise ValueError(f"Roster count '{name}' cannot be negative.")
        if not self.starting_slots():
            raise ValueError("A roster needs at least one starting slot.")

    def starting_slots(self) -> List[str]:
        """
        Starting slot names, e.g. ['QB1', 'RB1', 'RB2', ..., 'K', 'DEF'].

        Kicker and defense stay unnumbered when there is only one of each, which
        is what the existing roster panel and every test already expect. The
        numbering is cosmetic either way: `Team.add_player` matches slots by
        prefix, and the frontend strips trailing digits before choosing a hue.
        """
        slots: List[str] = []
        for name, stem in self._SLOT_ORDER:
            count = getattr(self, name)
            if count == 1 and stem in ('K', 'DEF'):
                slots.append(stem)
            else:
                slots.extend(f"{stem}{i}" for i in range(1, count + 1))
        return slots

    def slots(self, rounds: int) -> List[str]:
        """
        Every roster slot for a draft of `rounds` rounds: the starting lineup,
        then exactly enough bench to hold every pick that is not a starter.

        The bench has to be sized from the draft, not fixed. A hardcoded bench
        meant a 20-round draft had picks with nowhere to sit -- `add_player`
        tallies them but drops them off the roster panel -- while a short draft
        showed bench rows nobody could ever fill.
        """
        starters = self.starting_slots()
        bench = max(0, rounds - len(starters))
        return starters + [f"BN{i}" for i in range(1, bench + 1)]

    def position_slots(self) -> List[str]:
        """
        The starting lineup as bare positions, e.g. ['QB', 'RB', 'RB', ...].

        This is what `calculate_vorp` counts to find replacement level. FLEX and
        SFLEX stay in the list as themselves; the split across real positions is
        FLEX_SHARE / SUPERFLEX_SHARE, applied there.
        """
        return [slot.rstrip('0123456789') for slot in self.starting_slots()]

    def replacement_rank(self, position: str) -> int:
        """How deep the league starts at `position`. See `replacement_rank`."""
        return replacement_rank(position, self.teams, self.position_slots())

    @classmethod
    def from_payload(
        cls, teams: int | None = None, roster: Mapping[str, Any] | None = None
    ) -> "RosterSettings":
        """
        Builds settings from an API payload, where every field is optional.

        `teams` stays a top-level argument because it was one long before rosters
        were configurable, and the two draft-start endpoints already pass it.
        """
        known = {f.name for f in fields(cls)} - {'teams'}
        values: Dict[str, Any] = {}

        if roster:
            unknown = {k.lower() for k in roster} - known
            if unknown:
                raise ValueError(
                    f"Unknown roster setting(s): {', '.join(sorted(unknown))}. "
                    f"Valid settings: {', '.join(sorted(known))}."
                )
            values = {k.lower(): int(v) for k, v in roster.items()}

        if teams is not None:
            values['teams'] = int(teams)
        return cls(**values)

    def to_dict(self) -> Dict[str, int]:
        return {f.name: getattr(self, f.name) for f in fields(self)}
