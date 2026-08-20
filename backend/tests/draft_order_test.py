"""
Tests for the seating plan and the pick book.

Three claims, each of which the snake arithmetic this replaced got wrong.

A draft need not start snaking in round two -- and the parity test that assumed
it did silently mislabels every pick from round two on in a league that drafts
its first rounds in order.

A pick's owner is not a function of its position, because picks get traded.

A pick spent on a keeper is not made at all, so the clock steps over it and the
forward simulation must not play it out.
"""
import pytest

from backend.draft_order import DraftOrder, KeptPlayer, PickBook


def slots_in_round(order: DraftOrder, round_number: int):
    start = (round_number - 1) * order.teams
    return [order.slot_at(i) for i in range(start, start + order.teams)]


# --- the seating plan --------------------------------------------------------

def test_a_plain_snake_is_the_default():
    """
    `snake_from=2` is the definition of a snake, so every league that predates
    this setting keeps drafting exactly as it did.
    """
    order = DraftOrder(teams=12, rounds=4)

    assert slots_in_round(order, 1) == list(range(1, 13))
    assert slots_in_round(order, 2) == list(range(12, 0, -1))
    assert slots_in_round(order, 3) == list(range(1, 13))
    assert slots_in_round(order, 4) == list(range(12, 0, -1))


def test_snaking_can_start_later_than_round_two():
    """
    The UnderAchievers league: rounds 1-3 straight, reversing from round 4.

    Round 2 is the only round that differs from a plain snake, which is exactly
    what makes the old parity test so dangerous -- it is wrong in a way that
    looks right for eleven rounds out of twelve.
    """
    order = DraftOrder(teams=12, rounds=15, snake_from=4)

    assert slots_in_round(order, 1) == list(range(1, 13))
    assert slots_in_round(order, 2) == list(range(1, 13))
    assert slots_in_round(order, 3) == list(range(1, 13))
    assert slots_in_round(order, 4) == list(range(12, 0, -1))
    assert slots_in_round(order, 5) == list(range(1, 13))
    assert slots_in_round(order, 6) == list(range(12, 0, -1))


def test_the_turn_puts_the_same_seat_back_to_back():
    """
    Why a reversal follows the last straight round rather than alternating from
    round one: the straight round ends on the last seat, so the snaking round has
    to begin there.
    """
    order = DraftOrder(teams=12, rounds=6, snake_from=4)

    assert order.slot_at(35) == 12   # last pick of round 3
    assert order.slot_at(36) == 12   # first pick of round 4


def test_a_straight_draft_never_reverses():
    order = DraftOrder.straight(teams=10, rounds=5)
    for round_number in range(1, 6):
        assert slots_in_round(order, round_number) == list(range(1, 11))


@pytest.mark.parametrize("snake_from", [2, 4])
def test_a_seat_and_a_round_round_trip_to_a_pick(snake_from):
    order = DraftOrder(teams=12, rounds=15, snake_from=snake_from)
    for round_number in range(1, 16):
        for slot in range(1, 13):
            index = order.pick_index(round_number, slot)
            assert order.round_of(index) == round_number
            assert order.slot_at(index) == slot


def test_a_seat_outside_the_league_is_rejected_by_name():
    """
    The error has to say *which* number it wanted, because the natural mistake is
    writing the position within the round instead of the seat.
    """
    order = DraftOrder(teams=12, rounds=15)
    with pytest.raises(ValueError, match="manager's seat"):
        order.pick_index(3, 13)


# --- ownership ---------------------------------------------------------------

@pytest.fixture
def order():
    return DraftOrder(teams=4, rounds=3, snake_from=2)


def test_without_trades_a_seat_owns_its_own_picks(order):
    book = PickBook(order)
    assert book.picks_for(0) == [1, 8, 9]


def test_a_traded_pick_changes_hands(order):
    """
    The claim the arithmetic could not make. Seat 1's round-3 pick belongs to
    seat 4, and nothing about its position says so.
    """
    book = PickBook.build(order, trades=[{"round": 3, "pick": 1, "traded_to": 4}])

    assert book.owner_of(order.pick_index(3, 1)) == 3
    assert book.picks_for(0) == [1, 8]
    assert 9 in book.picks_for(3)


def test_a_trade_can_name_a_manager(order):
    book = PickBook.build(
        order,
        trades=[{"round": 2, "pick": 2, "traded_to": "Andy"}],
        slot_of={"George": 1, "Andy": 3},
    )
    assert book.owner_of(order.pick_index(2, 2)) == 2


def test_an_unknown_manager_is_refused_with_the_known_ones(order):
    with pytest.raises(ValueError, match="Unknown manager 'Nobody'.*George"):
        PickBook.build(
            order,
            trades=[{"round": 2, "pick": 2, "traded_to": "Nobody"}],
            slot_of={"George": 1},
        )


def test_a_pick_traded_twice_is_refused(order):
    """Silently keeping one of the two would hand the pick to the wrong roster."""
    with pytest.raises(ValueError, match="traded twice"):
        PickBook.build(order, trades=[
            {"round": 2, "pick": 2, "traded_to": 1},
            {"round": 2, "pick": 2, "traded_to": 3},
        ])


# --- keepers -----------------------------------------------------------------

def kept(order, player, round_number, slot, team_index):
    return KeptPlayer(
        player=player,
        normalized_name=player.lower().replace(" ", "_"),
        pick_index=order.pick_index(round_number, slot),
        team_index=team_index,
    )


def test_a_kept_pick_is_not_one_of_your_picks(order):
    book = PickBook(order).with_keepers([kept(order, "A Keeper", 1, 1, 0)])

    assert book.picks_for(0) == [8, 9]
    assert book.is_kept(0)


def test_the_clock_steps_over_kept_picks(order):
    """
    A draft whose first two picks are keepers opens on pick three. Stopping on
    one would wait forever for a pick nobody is going to make.
    """
    book = PickBook(order).with_keepers([
        kept(order, "First", 1, 1, 0),
        kept(order, "Second", 1, 2, 1),
    ])

    assert book.next_open_pick(0) == 2
    assert book.next_open_pick(2) == 2


def test_the_clock_runs_out_when_the_tail_is_all_keepers(order):
    """Returns the total, which is what every completion check compares against."""
    book = PickBook(order).with_keepers([kept(order, "Last", 3, 4, 3)])
    assert book.next_open_pick(11) == 12 == book.total_picks


def test_two_keepers_on_one_pick_are_refused(order):
    with pytest.raises(ValueError, match="One pick keeps one player"):
        PickBook(order).with_keepers([
            kept(order, "One", 2, 2, 1),
            kept(order, "Two", 2, 2, 1),
        ])


def test_the_simulated_span_skips_keepers_and_follows_trades(order):
    """
    What the VONA forward simulation plays out. A keeper in the span is already
    made, and a traded pick belongs to somebody else -- simulating either wrongly
    drains a player who was never going anywhere, or reads the wrong team's needs.
    """
    book = PickBook.build(order, trades=[{"round": 1, "pick": 3, "traded_to": 2}])
    book = book.with_keepers([kept(order, "Kept", 1, 2, 1)])

    # Round one, seat by seat: seat 1 picks, seat 2's is a keeper and drops out,
    # seat 3's now belongs to seat 2, seat 4 picks. Team indices are 0-based.
    assert book.open_picks_between(0, 4) == [0, 1, 3]


def test_picks_remaining_counts_the_picks_a_team_actually_has(order):
    """
    Not `rounds - picks_made`. A manager who traded a pick away has fewer, and on
    the derived count never reaches the endgame window where the CPU fills its
    kicker and defense slots.
    """
    book = PickBook.build(order, trades=[{"round": 3, "pick": 1, "traded_to": 4}])
    book = book.with_keepers([kept(order, "Kept", 1, 1, 0)])

    # Seat 1 keeps one, trades one away, so one live pick is left of three rounds.
    assert book.picks_remaining(0, 0) == 1
    assert book.picks_remaining(3, 0) == 4
