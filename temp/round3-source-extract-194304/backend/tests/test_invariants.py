import pytest

from backend.app.domain.room import Room, new_player
from backend.app.domain.cards import build_core_uno_deck
from backend.app.engine.invariants import InvariantError, assert_room_invariants


def test_duplicate_card_location_is_rejected():
    host = new_player("host", 0, is_host=True)
    other = new_player("other", 1)
    card = build_core_uno_deck()[0]
    host.hand.append(card)
    other.hand.append(card)
    room = Room(room_id="ABC123", host_player_id=host.player_id, players=[host, other])
    with pytest.raises(InvariantError):
        assert_room_invariants(room)

