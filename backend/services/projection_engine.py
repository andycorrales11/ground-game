"""
Turns projection inputs into fantasy points, for whatever a league pays.

This is the piece that replaces a precomputed projection column. The old board
read `ppr_proj_pts` out of the database -- a number somebody else calculated
under somebody else's scoring rules -- so a league that paid 6 for a passing
touchdown drafted off a board that paid 4. Here, volume and rates come from the
data and the *scoring* comes from the league, so the board is the league's own.

Everything in this module is a pure function of (inputs, settings). No database,
no dataframes, no globals. That is what lets the parity tests hammer it against
the workbook's own cached values at 1e-9 (see `projection_engine_test.py`).

Two formula asymmetries are easy to get wrong and are load-bearing (spec §3.3):

- Passing **yards and touchdowns derive from completions**; interceptions derive
  from attempts. They are not all per-attempt rates.
- The receiving-touchdown rate is **raw, per reception**. Unlike rush and target
  share, it is not renormalized, so one player's rate does not dilute anyone
  else's.
"""
from dataclasses import dataclass, field, fields
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Tuple

from backend.league import ScoringSettings

# Rushing and target shares are scaled to 98%, leaving a deliberate 2% for the
# players nobody bothers to list -- practice-squad callups, a third tight end who
# catches four passes all year. Pass share is *not* scaled: every pass attempt
# has to be thrown by one of the listed quarterbacks.
UNLISTED_LEAKAGE = 0.98

# Positions excluded from each volume type, by what the workbook's share
# denominators actually span (spec §3.2). Tight ends are outside the rushing
# denominator and quarterbacks outside the target denominator, so a team's
# shares add up over exactly the players who can claim them.
RUSH_POSITIONS = ('QB', 'RB', 'WR')
TARGET_POSITIONS = ('RB', 'WR', 'TE')
PASS_POSITIONS = ('QB',)


@dataclass(frozen=True)
class PlayerRates:
    """
    One player's inputs: a share weight per volume type, and the efficiency rates
    that turn volume into production.

    Every rate defaults to zero, because the sources leave them blank wherever
    they cannot apply -- a tight end has no rushing rates, a quarterback has no
    catch rate. Zero and blank mean the same thing to every formula that reads
    them, so the distinction is not worth carrying.

    `key` identifies the player within their team. It is the workbook's row
    number when these come from the workbook, and it stays an opaque integer
    everywhere else -- nothing computes with it, it only has to be unique per
    team so a projected line can be handed back to the player it belongs to.
    """

    team: str
    key: int
    name: str
    pos: str

    # Relative share weights. Normalized by `project_team`, never pre-normalized
    # by whatever produced them.
    w_pass: float = 0.0
    w_rush: float = 0.0
    w_tgt: float = 0.0

    # Passing rates. Note `yds_per_comp` and `pass_td_pct` are per *completion*
    # while `int_pct` is per *attempt*.
    comp_pct: float = 0.0
    yds_per_comp: float = 0.0
    pass_td_pct: float = 0.0
    int_pct: float = 0.0

    # Rushing rates. `rush_ypc` is the player's own, overriding the team figure.
    rush_ypc: float = 0.0
    rush_td_rate: float = 0.0

    # Receiving rates. `rec_td_rate` is per reception, raw.
    catch_rate: float = 0.0
    yds_per_rec: float = 0.0
    rec_td_rate: float = 0.0

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "PlayerRates":
        """Builds from a database row or CSV record, ignoring extra columns."""
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in record.items() if k in known}
        return cls(
            team=str(values.pop('team')),
            key=int(values.pop('key')),
            name=str(values.pop('name')),
            pos=str(values.pop('pos')),
            **{k: float(v if v is not None else 0.0) for k, v in values.items()},
        )


@dataclass(frozen=True)
class TeamVolume:
    """
    A team's offensive budget for the season: how many plays it runs and how it
    splits them.

    `rush_ypc` is the team-level default; individual players carry their own and
    the engine uses theirs. It is kept because it is a real input and because a
    team with no listed rushers still has a rushing profile.
    """

    team: str
    plays: float
    pass_pct: float
    rush_ypc: float

    @property
    def pass_attempts(self) -> float:
        return self.plays * self.pass_pct

    @property
    def rush_attempts(self) -> float:
        return self.plays * (1.0 - self.pass_pct)

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "TeamVolume":
        return cls(
            team=str(record['team']),
            plays=float(record['plays']),
            pass_pct=float(record['pass_pct']),
            rush_ypc=float(record['rush_ypc'] or 0.0),
        )


@dataclass(frozen=True)
class ProjectionInputs:
    """
    Everything the engine needs, whatever produced it.

    The workbook is one source (`backend/ingest/workbook.py`); the database is
    the other, and is what the running app uses. The engine cannot tell them
    apart, which is the point -- it never learns where a rate came from.
    """

    volumes: Dict[str, TeamVolume] = field(default_factory=dict)
    players: List[PlayerRates] = field(default_factory=list)

    def by_team(self) -> Iterator[Tuple[TeamVolume, List[PlayerRates]]]:
        """
        Each team's volume paired with its players.

        Grouped rather than filtered per team so that a large player list does
        not turn this into a quadratic scan.
        """
        grouped: Dict[str, List[PlayerRates]] = {}
        for player in self.players:
            grouped.setdefault(player.team, []).append(player)

        for team, volume in self.volumes.items():
            yield volume, grouped.get(team, [])


@dataclass(frozen=True)
class StatLine:
    """
    A projected season for one player.

    Every position uses the same shape, with the categories that cannot apply
    left at zero -- a tight end's rushing line, a quarterback's receiving line.
    That is what lets `score` be a single dot product instead of four
    position-specific ones.
    """

    pass_attempts: float = 0.0
    completions: float = 0.0
    pass_yards: float = 0.0
    pass_tds: float = 0.0
    interceptions: float = 0.0

    rush_attempts: float = 0.0
    rush_yards: float = 0.0
    rush_tds: float = 0.0

    targets: float = 0.0
    receptions: float = 0.0
    recv_yards: float = 0.0
    recv_tds: float = 0.0


@dataclass(frozen=True)
class ProjectedPlayer:
    """A player's identity, projected line, and what it is worth."""

    team: str
    name: str
    pos: str
    key: int
    line: StatLine
    points: float


def _share(weight: float, total: float, scale: float = 1.0) -> float:
    """
    One player's cut of a team's volume.

    The editable weights are *relative*, not percentages -- they get renormalized
    against their column's total, which is why bumping one player's target share
    automatically dilutes his teammates. A team with no weights at all gets zero
    rather than a division error; that team simply has nobody listed to claim the
    volume.
    """
    return (weight / total) * scale if total else 0.0


def project_team(volume: TeamVolume, players: Iterable[PlayerRates]) -> Dict[int, StatLine]:
    """
    Projects one team's stat lines, keyed by each player's `key`.

    Volume is allocated top-down: the team's play count splits into pass and rush
    attempts, and each player claims a normalized share. Rates then turn volume
    into production.
    """
    players = list(players)

    team_pass_attempts = volume.pass_attempts
    team_rush_attempts = volume.rush_attempts

    total_pass_weight = sum(p.w_pass for p in players)
    total_rush_weight = sum(p.w_rush for p in players if p.pos in RUSH_POSITIONS)
    total_target_weight = sum(p.w_tgt for p in players if p.pos in TARGET_POSITIONS)

    # Targets are shares of what the quarterbacks actually throw, which is not
    # quite the team's pass-attempt total: pass share is unscaled and sums to
    # 1.0 only when every attempt is accounted for by a listed quarterback.
    quarterback_attempts = sum(
        team_pass_attempts * _share(p.w_pass, total_pass_weight)
        for p in players if p.pos in PASS_POSITIONS
    )

    lines: Dict[int, StatLine] = {}
    for player in players:
        values: Dict[str, float] = {}

        if player.pos in PASS_POSITIONS:
            attempts = team_pass_attempts * _share(player.w_pass, total_pass_weight)
            completions = attempts * player.comp_pct
            values.update(
                pass_attempts=attempts,
                completions=completions,
                # Yards and touchdowns are per *completion*; an interception can
                # only happen on an attempt. The workbook is right about this and
                # it is the first thing a rewrite gets wrong.
                pass_yards=completions * player.yds_per_comp,
                pass_tds=completions * player.pass_td_pct,
                interceptions=attempts * player.int_pct,
            )

        if player.pos in RUSH_POSITIONS:
            carries = team_rush_attempts * _share(
                player.w_rush, total_rush_weight, UNLISTED_LEAKAGE
            )
            values.update(
                rush_attempts=carries,
                # The player's own yards per carry, not the team's. The team
                # figure is a profile; this is the one that produces yards.
                rush_yards=carries * player.rush_ypc,
                rush_tds=carries * player.rush_td_rate,
            )

        if player.pos in TARGET_POSITIONS:
            targets = quarterback_attempts * _share(
                player.w_tgt, total_target_weight, UNLISTED_LEAKAGE
            )
            receptions = targets * player.catch_rate
            values.update(
                targets=targets,
                receptions=receptions,
                recv_yards=receptions * player.yds_per_rec,
                # Raw rate, deliberately un-normalized. Editing this does not
                # dilute teammates, which is why the team-level touchdown balance
                # is only a convention and not an invariant -- see check_team_
                # touchdown_balance.
                recv_tds=receptions * player.rec_td_rate,
            )

        lines[player.key] = StatLine(**values)

    return lines


def score(line: StatLine, pos: str, scoring: ScoringSettings) -> float:
    """
    What a projected line is worth under a league's scoring.

    One dot product covers every position because the categories a position
    cannot produce are already zero in its line. The only per-position term is
    the reception, which real leagues do value differently by position.
    """
    return (
        line.pass_attempts * scoring.pass_attempts
        + line.completions * scoring.completions
        + line.pass_yards * scoring.pass_yards
        + line.pass_tds * scoring.pass_tds
        + line.interceptions * scoring.interceptions
        + line.rush_attempts * scoring.rush_attempts
        + line.rush_yards * scoring.rush_yards
        + line.rush_tds * scoring.rush_tds
        + line.targets * scoring.targets
        + line.receptions * scoring.receptions_for(pos)
        + line.recv_yards * scoring.recv_yards
        + line.recv_tds * scoring.recv_tds
    )


def project_all(
    inputs: ProjectionInputs, scoring: ScoringSettings
) -> List[ProjectedPlayer]:
    """
    Projects and scores every player, in workbook order.

    This is the whole engine in one call, and it is cheap -- a few hundred
    players of trivial arithmetic. Recompute it whenever anything changes rather
    than tracking what depends on what; the spreadsheet needs a dependency graph
    because it is a spreadsheet.
    """
    projected: List[ProjectedPlayer] = []
    for volume, players in inputs.by_team():
        lines = project_team(volume, players)
        for player in players:
            line = lines[player.key]
            projected.append(ProjectedPlayer(
                team=player.team,
                name=player.name,
                pos=player.pos,
                key=player.key,
                line=line,
                points=score(line, player.pos, scoring),
            ))
    return projected



STAT_FIELDS = tuple(f.name for f in fields(StatLine))
