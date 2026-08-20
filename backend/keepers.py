"""
What the league decided before the draft started: keepers, and traded picks.

Both come from JSON on disk, next to the ADP files, because both are facts about
one particular league rather than about football. `data/keepers.json` and
`data/trades.json`; see `_load_json` for the shapes.

**Picks are named by seat, never by position within the round.** A keeper is
written `{"player": ..., "round": 5, "pick": 10}` where `pick` is the manager's
draft slot -- so manager 10 is "pick 10" in every round, and filling the file in
never requires working out which direction that round runs. `DraftOrder` does
that conversion, which is also what lets a league snake from a round other than
the second without any of this changing.

**A keeper that cannot be resolved is an error, not a skip.** Everything else
here is soft -- no files, no keepers, fine -- but a keeper silently failing to
apply would leave the player on the board *and* leave his pick live, which is two
wrong answers compounding for the rest of the draft. Better to refuse to start.
"""
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping

from backend.draft_order import DraftOrder, KeptPlayer, PickBook
from backend.utils import normalize_name

KEEPERS_FILE = "keepers.json"
TRADES_FILE = "trades.json"


@dataclass(frozen=True)
class LeagueBook:
    """The raw contents of the two files, before they are resolved to a board."""

    keepers: List[Dict[str, Any]] = field(default_factory=list)
    trades: List[Dict[str, Any]] = field(default_factory=list)
    managers: Dict[str, int] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.keepers or self.trades)

    def describe(self) -> str:
        return f"{len(self.keepers)} keeper(s), {len(self.trades)} traded pick(s)"


def _load_json(path: Path):
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path.name} is not valid JSON: {error}") from error


def load(data_dir: Path) -> LeagueBook:
    """
    Reads both files. Missing files are not an error -- a league without keepers
    is the normal case, and every mock draft is one.

    `keepers.json` is a list of `{player, round, pick, manager?}`.

    `trades.json` is either a bare list of `{round, pick, traded_to}` or an object
    `{"managers": {name: slot}, "trades": [...]}`. The managers map is what lets
    `traded_to` name a person rather than a seat number, which is how a draft
    sheet is actually written.
    """
    keepers = _load_json(Path(data_dir) / KEEPERS_FILE) or []
    if not isinstance(keepers, list):
        raise ValueError(f"{KEEPERS_FILE} must be a list of keeper entries.")

    raw_trades = _load_json(Path(data_dir) / TRADES_FILE)
    managers: Dict[str, int] = {}
    if raw_trades is None:
        trades: List[Dict[str, Any]] = []
    elif isinstance(raw_trades, list):
        trades = raw_trades
    elif isinstance(raw_trades, dict):
        trades = raw_trades.get("trades", []) or []
        managers = {str(k): int(v) for k, v in (raw_trades.get("managers") or {}).items()}
    else:
        raise ValueError(f"{TRADES_FILE} must be a list or an object with 'trades'.")

    return LeagueBook(keepers=list(keepers), trades=list(trades), managers=managers)


def _require(entry: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in entry:
        raise ValueError(f"{where} is missing '{key}': {json.dumps(entry)}")
    return entry[key]


def build_pick_book(
    order: DraftOrder,
    book: LeagueBook,
    board_names: Mapping[str, str] | None = None,
) -> PickBook:
    """
    Turns the two files into a `PickBook`: owners after trades, keepers resolved.

    `board_names` maps a normalized name to the board's display name. When it is
    given, every keeper must be in it -- see the module docstring for why an
    unresolved keeper refuses to start the draft rather than being dropped.

    A keeper's owner comes from the pick, *after* trades. That is the whole
    reason the two files compose: the draft sheet writes a kept player in the
    seat that originally held the pick and notes the new owner beside it, so
    Caleb Williams sits in Adrian's round-5 row and belongs to Andy.
    """
    picks = PickBook.build(order, book.trades, book.managers)
    slot_of = book.managers
    manager_at = {slot - 1: name for name, slot in slot_of.items()}

    resolved: List[KeptPlayer] = []
    unresolved: List[str] = []

    for entry in book.keepers:
        where = f"keepers.json entry {json.dumps(entry)}"
        player = str(_require(entry, "player", where)).strip()
        index = order.pick_index(
            int(_require(entry, "round", where)), int(_require(entry, "pick", where))
        )
        normalized = normalize_name(player)

        if board_names is not None and normalized not in board_names:
            unresolved.append(f"{order.label(index)} {player}")
            continue

        team_index = picks.owner_of(index)

        # An optional cross-check. The sheet already knows who ends up with the
        # player, so when the file carries that it is free evidence that the
        # trades are right -- and a mismatch means one of the two is wrong in a
        # way nothing downstream could ever notice.
        stated = entry.get("manager")
        if stated and slot_of:
            expected = manager_at.get(team_index)
            if expected and str(stated).strip().lower() != expected.lower():
                raise ValueError(
                    f"{order.label(index)} {player}: the file says {stated} keeps "
                    f"him, but that pick belongs to {expected}. Either the keeper's "
                    f"round/pick or the trade on that pick is wrong."
                )

        resolved.append(
            KeptPlayer(
                player=board_names[normalized] if board_names else player,
                normalized_name=normalized,
                pick_index=index,
                team_index=team_index,
                manager=str(stated).strip() if stated else manager_at.get(team_index),
            )
        )

    if unresolved:
        raise ValueError(
            "These keepers are not on the board, so the draft cannot start:\n  "
            + "\n  ".join(unresolved)
            + "\nCheck the spelling against the players table, or re-run the ingest "
              "if the player is new."
        )

    duplicates = _duplicate_players(resolved)
    if duplicates:
        raise ValueError(
            "The same player is kept more than once: " + ", ".join(duplicates)
        )

    return picks.with_keepers(resolved)


def _duplicate_players(keepers: List[KeptPlayer]) -> List[str]:
    seen: Dict[str, KeptPlayer] = {}
    clashes = []
    for keeper in keepers:
        other = seen.get(keeper.normalized_name)
        if other:
            clashes.append(f"{keeper.player} ({other.manager} and {keeper.manager})")
        seen[keeper.normalized_name] = keeper
    return clashes


def log_pick_book(picks: PickBook) -> None:
    """
    Prints every keeper as it was understood.

    This is the check that matters on draft morning, and it is cheap: the file is
    written by hand off a spreadsheet, and the failure it guards against -- a
    round or a seat off by one -- produces a perfectly valid draft that quietly
    belongs to the wrong person. Reading twelve lines back beats discovering it
    at pick 40.
    """
    keepers = picks.keepers()
    if not keepers:
        return

    logging.info("Keepers applied (%d):", len(keepers))
    for keeper in keepers:
        logging.info(
            "  %-7s overall %3d  %-22s %s",
            picks.order.label(keeper.pick_index),
            keeper.pick_index + 1,
            keeper.player,
            keeper.manager or f"team {keeper.team_index + 1}",
        )
