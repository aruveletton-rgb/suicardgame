import pytest

from backend.app.domain.room import Room, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command


def make_started_room():
    host = new_player("host", 0, is_host=True)
    guest = new_player("guest", 1)
    room = Room(room_id="TEST01", host_player_id=host.player_id, players=[host, guest])
    process_command(room, Command(action_id="guest-ready", room_id=room.room_id, player_id=guest.player_id, command_type="READY"))
    process_command(
        room,
        Command(
            action_id="start",
            room_id=room.room_id,
            player_id=host.player_id,
            command_type="START_GAME",
            payload={"seed": 17},
        ),
    )
    return room, host, guest


def test_test_state_command_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("TEST_MODE", raising=False)
    room, host, _guest = make_started_room()

    with pytest.raises(CommandError) as exc_info:
        process_command(
            room,
            Command(
                action_id="test-state-disabled",
                room_id=room.room_id,
                player_id=host.player_id,
                command_type="TEST_SET_STATE",
                payload={},
            ),
        )

    assert exc_info.value.code == "TEST_MODE_DISABLED"


def test_test_state_command_builds_deterministic_hands_only_in_test_mode(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    room, host, guest = make_started_room()

    result = process_command(
        room,
        Command(
            action_id="test-state-enabled",
            room_id=room.room_id,
            player_id=host.player_id,
            command_type="TEST_SET_STATE",
            payload={
                "current_player_id": host.player_id,
                "discard_asset_key": "uno_red_5",
                "hands": {
                    host.player_id: ["uno_wild_draw_four", "uno_red_7", "sui_ling"],
                    guest.player_id: ["uno_blue_2"],
                },
                "deck_asset_keys": [
                    "uno_green_1",
                    "uno_yellow_2",
                    "uno_blue_3",
                    "uno_red_4",
                    "uno_green_5",
                    "uno_yellow_6",
                ],
            },
        ),
    )

    game = room.active_game
    assert game is not None
    assert result["test_mode"] is True
    assert [card.asset_key for card in host.hand] == ["uno_wild_draw_four", "uno_red_7", "sui_ling"]
    assert [card.asset_key for card in guest.hand] == ["uno_blue_2"]
    assert game.discard_pile[-1].asset_key == "uno_red_5"
    assert game.current_player_id == host.player_id
