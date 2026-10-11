import pytest

from backend.app.domain.cards import Card, CardCategory, CardSpec, SPECIAL_BY_KIND, build_game_deck
from backend.app.domain.room import Room, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command


def test_retired_nian_card_is_not_in_current_decks_or_special_registry():
    for player_count in (2, 3, 4, 5):
        deck, field = build_game_deck(player_count)
        assert all(card.kind != "nian" for card in [*deck, *field])
    assert "nian" not in SPECIAL_BY_KIND


def test_retired_nian_card_cannot_be_activated_or_enable_claim_rules():
    host = new_player("host", 0, is_host=True)
    guest = new_player("guest", 1)
    room = Room(room_id="OLD001", host_player_id=host.player_id, players=[host, guest])
    for player in room.players:
        process_command(room, Command(f"ready-{player.player_id}", room.room_id, player.player_id, "READY"))
    process_command(room, Command("start", room.room_id, host.player_id, "START_GAME", {"seed": 17}))

    retired_nian = Card.from_spec(
        CardSpec(CardCategory.SUI, "nian", "sui_nian", display_name="年牌")
    )
    host.hand = [retired_nian]
    with pytest.raises(CommandError) as exc_info:
        process_command(
            room,
            Command("activate-retired-nian", room.room_id, host.player_id, "ACTIVATE_SPECIAL", {"card_id": retired_nian.card_id}),
        )

    assert exc_info.value.code == "NOT_SPECIAL_CARD"
    assert room.active_game is not None
    assert room.active_game.special_state.get("nian") is None
