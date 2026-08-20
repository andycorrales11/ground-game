"""
Who is on the clock, and who owns the pick.

Both used to be arithmetic. `current_round % 2 == 0` reversed the order, and the
team on the clock was `current_pick_num % teams` -- reimplemented in five places,
which CLAUDE.md warned about but did not fix. That arithmetic can only express
one thing: a pure snake in which every manager owns every one of their own picks.

Two facts about a real keeper league break it outright.

**Picks get traded.** A pick's owner is then not derivable from its position at
all. It is a fact you have to look up, so this module holds a list rather than a
formula.

**The snake need not start in round two.** A league can run its first few rounds
in a straight line and only then begin snaking -- which is what the UnderAchievers
league does, rounds 1 to 3 in order and reversing from round 4. Under the old
parity test, round 2 reversed and every pick number from there on was wrong.

Everything here is deliberately indexed the way the rest of the app already is:
**`pick_index` is 0-based** (it indexes the same sequence as the live mode's
`picks_order`, and equals `current_pick_num` for the pick on the clock), while
**pick *numbers* handed to callers are 1-based**, matching
`user_picks_simulation`. Slots and rounds are 1-based, as anyone reading a draft
board would expect.
"""
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence

# The round a plain snake first reverses. Round 2, by definition -- so this is the
# default, and every league that has ever run through this code behaves exactly
# as it did before `snake_from` existed.
PLAIN_SNAKE_FROM = 2


@dataclass(frozen=True)
class DraftOrder:
    """
    The seating plan: which slot picks at which point, before any trades.

    `snake_from` is the first round that runs backwards. A plain snake is 2. A
    league that drafts rounds 1-3 in order and snakes from round 4 is 4, and a
    straight draft that never reverses is any round past the end.

    The rule that a round reverses when `(round - snake_from)` is even is not a
    parity trick -- it follows from the turn. The last linear round ends on the
    final slot, so the first snaking round has to begin there too, which makes it
    a reversed round. Everything after alternates from that.
    """

    teams: int
    rounds: int
    snake_from: int = PLAIN_SNAKE_FROM

    def __post_init__(self):
        if self.teams < 1:
            raise ValueError(f"A draft needs at least one team, got {self.teams}.")
        if self.rounds < 1:
            raise ValueError(f"A draft needs at least one round, got {self.rounds}.")

    @classmethod
    def straight(cls, teams: int, rounds: int) -> "DraftOrder":
        """An order that never reverses -- slot 1 picks first in every round."""
        return cls(teams=teams, rounds=rounds, snake_from=rounds + 1)

    @property
    def total_picks(self) -> int:
        return self.teams * self.rounds

    def is_reversed(self, round_number: int) -> bool:
        if round_number < self.snake_from:
            return False
        return (round_number - self.snake_from) % 2 == 0

    def round_of(self, pick_index: int) -> int:
        return pick_index // self.teams + 1

    def slot_at(self, pick_index: int) -> int:
        """The 1-based draft slot on the clock at a 0-based pick index."""
        within = pick_index % self.teams
        if self.is_reversed(self.round_of(pick_index)):
            return self.teams - within
        return within + 1

    def pick_index(self, round_number: int, slot: int) -> int:
        """
        The 0-based pick index of a given slot's pick in a given round.

        This is the direction the keeper and trade files are written in: they name
        a seat and a round, never a position within the round, so that filling one
        in never requires working out which way that round runs.
        """
        if not 1 <= round_number <= self.rounds:
            raise ValueError(
                f"Round {round_number} is outside a {self.rounds}-round draft."
            )
        if not 1 <= slot <= self.teams:
            raise ValueError(
                f"Pick {slot} is not a draft slot in a {self.teams}-team league. "
                f"This is the manager's seat (1-{self.teams}), not the position "
                f"within the round."
            )
        within = (self.teams - slot) if self.is_reversed(round_number) else (slot - 1)
        return (round_number - 1) * self.teams + within

    def label(self, pick_index: int) -> str:
        """`R5 P10` -- round and seat, the way the draft sheet reads."""
        return f"R{self.round_of(pick_index)} P{self.slot_at(pick_index)}"


@dataclass(frozen=True)
class KeptPlayer:
    """A keeper, resolved to the pick it consumes and the team that owns it."""

    player: str
    normalized_name: str
    pick_index: int
    team_index: int
    manager: str | None = None


class PickBook:
    """
    Every pick in the draft: who owns it, and whether it is already spent.

    Owners are **team indices** (0-based, so slot 1 is index 0), because that is
    what indexes `teams_list`. A traded pick simply has a different index stored
    against it; nothing downstream needs to know a trade happened.

    Keepers are held here rather than in the session because they are a property
    of the picks. A kept pick is one nobody gets to make: the player is off the
    board before the draft starts, and the clock steps straight over it.
    """

    def __init__(
        self,
        order: DraftOrder,
        owners: Sequence[int] | None = None,
        keepers: Mapping[int, KeptPlayer] | None = None,
        managers: Mapping[str, int] | None = None,
    ):
        self.order = order
        # Seat -> the person sitting in it, when the league named them. Kept here
        # because this is already what resolves a name in a trade, and because a
        # results table that says "Team 7" when the league calls him Janson is
        # asking the reader to do the lookup themselves.
        self._manager_at: Dict[int, str] = {
            int(slot) - 1: name for name, slot in (managers or {}).items()
        }
        self._owners: List[int] = (
            list(owners) if owners is not None
            else [order.slot_at(i) - 1 for i in range(order.total_picks)]
        )
        self._keepers: Dict[int, KeptPlayer] = dict(keepers or {})

    # --- construction ---------------------------------------------------------

    @classmethod
    def build(
        cls,
        order: DraftOrder,
        trades: Iterable[Mapping] = (),
        slot_of: Mapping[str, int] | None = None,
    ) -> "PickBook":
        """
        A book with trades applied. Keepers are added afterwards, once their names
        have been resolved against the board.

        `trades` are `{round, pick, traded_to}` where `pick` is the seat that
        originally owned it. `traded_to` is a manager name resolved through
        `slot_of`, or a slot number for a league that never named its managers.
        """
        book = cls(order, managers=slot_of)
        seen: Dict[int, Mapping] = {}

        for trade in trades:
            index = order.pick_index(int(trade['round']), int(trade['pick']))
            if index in seen:
                raise ValueError(
                    f"{order.label(index)} is traded twice. A pick has one owner; "
                    f"if it changed hands more than once, keep only the last."
                )
            seen[index] = trade
            book._owners[index] = _resolve_team_index(
                trade['traded_to'], order.teams, slot_of
            )

        return book

    def with_keepers(self, keepers: Iterable[KeptPlayer]) -> "PickBook":
        """A copy carrying these keepers. Rejects two keepers on one pick."""
        placed: Dict[int, KeptPlayer] = {}
        for keeper in keepers:
            if keeper.pick_index in placed:
                raise ValueError(
                    f"Two keepers on {self.order.label(keeper.pick_index)}: "
                    f"{placed[keeper.pick_index].player} and {keeper.player}. "
                    f"One pick keeps one player."
                )
            placed[keeper.pick_index] = keeper
        return PickBook(self.order, self._owners, placed, self.managers())

    # --- reading --------------------------------------------------------------

    @property
    def total_picks(self) -> int:
        return self.order.total_picks

    def managers(self) -> Dict[str, int]:
        """The seat each named manager holds, 1-based -- the form the files use."""
        return {name: index + 1 for index, name in self._manager_at.items()}

    def manager_name(self, team_index: int) -> str | None:
        """What the league calls this team, or None if it never said."""
        return self._manager_at.get(team_index)

    def owner_of(self, pick_index: int) -> int:
        """The 0-based team index on the clock at a 0-based pick index."""
        return self._owners[pick_index]

    def keeper_at(self, pick_index: int) -> KeptPlayer | None:
        return self._keepers.get(pick_index)

    def is_kept(self, pick_index: int) -> bool:
        return pick_index in self._keepers

    def keepers(self) -> List[KeptPlayer]:
        """Every keeper, in pick order."""
        return [self._keepers[i] for i in sorted(self._keepers)]

    def keepers_for(self, team_index: int) -> List[KeptPlayer]:
        return [k for k in self.keepers() if k.team_index == team_index]

    def next_open_pick(self, pick_index: int) -> int:
        """
        The first pick from here on that somebody actually makes.

        Keeper picks are already spent, so the clock steps over them rather than
        stopping on one. Returns `total_picks` when the draft is finished, which
        is what every completion check already compares against.
        """
        while pick_index < self.total_picks and self.is_kept(pick_index):
            pick_index += 1
        return pick_index

    def picks_for(self, team_index: int) -> List[int]:
        """
        A team's remaining pick **numbers**, 1-based, keeper picks excluded.

        1-based because this is what feeds `user_picks_simulation`, which has
        always been 1-based, and because it is what a draft board shows.
        """
        return [
            index + 1
            for index in range(self.total_picks)
            if self._owners[index] == team_index and not self.is_kept(index)
        ]

    def picks_remaining(self, team_index: int, from_index: int) -> int:
        """
        How many picks this team still has to make from `from_index` onwards.

        Trades make this genuinely different from `rounds - picks_made`, which is
        what the CPU's endgame logic used to assume. A manager who traded three
        picks away has twelve in a fifteen-round draft, and on the old count never
        reached the final-rounds window that makes a team fill its kicker and
        defense slots -- so they finished the draft without either.
        """
        return sum(
            1
            for index in range(max(0, from_index), self.total_picks)
            if self._owners[index] == team_index and not self.is_kept(index)
        )

    def open_picks_between(self, start_index: int, end_index: int) -> List[int]:
        """
        Team indices for the picks actually made in `[start_index, end_index)`.

        This is what the VONA forward simulation plays out. It must be the real
        sequence and not a count: keeper picks in the span are already made, so
        simulating them would drain players who are not going anywhere, and a
        traded pick belongs to a different roster, so simulating it against the
        wrong team gets that team's positional need wrong.
        """
        return [
            self._owners[index]
            for index in range(max(0, start_index), min(end_index, self.total_picks))
            if not self.is_kept(index)
        ]


def _resolve_team_index(
    who, teams: int, slot_of: Mapping[str, int] | None
) -> int:
    """
    A manager name or a slot number to a 0-based team index.

    Names are how a draft sheet is actually written, so they are the primary
    form. An unknown one raises and lists what it could have been: a silently
    dropped trade would hand a pick to the wrong roster for the whole draft.
    """
    if isinstance(who, str):
        key = who.strip()
        if slot_of and key in slot_of:
            return int(slot_of[key]) - 1
        if slot_of:
            lowered = {name.lower(): slot for name, slot in slot_of.items()}
            if key.lower() in lowered:
                return int(lowered[key.lower()]) - 1
        if not key.lstrip('-').isdigit():
            known = ', '.join(sorted(slot_of)) if slot_of else 'none declared'
            raise ValueError(
                f"Unknown manager '{who}'. Known managers: {known}."
            )
        who = int(key)

    slot = int(who)
    if not 1 <= slot <= teams:
        raise ValueError(
            f"Draft slot {slot} is outside a {teams}-team league."
        )
    return slot - 1
