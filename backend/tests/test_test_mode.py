import pytest

from backend.app.domain.room import Room, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.tests.ready_helpers import ready_all


def make_started_room():
    host = new_player("host", 0, is_host=True)
    guest = new_player("guest", 1)
    room = Room(room_id="TEST01", host_player_id=host.player_id, players=[host, guest])
    ready_all(room)
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


def test_test_state_can_seed_a_valid_action_stack(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    room, host, guest = make_started_room()
    process_command(room, Command(
        "seed-stack", room.room_id, host.player_id, "TEST_SET_STATE", {
            "current_player_id": guest.player_id,
            "discard_asset_key": "uno_red_draw_two",
            "hands": {host.player_id: ["uno_blue_7"], guest.player_id: ["uno_blue_draw_two"]},
            "action_stack": {"kind": "draw_two", "count": 4},
        },
    ))
    assert room.active_game.special_state["action_stack"] == {"kind": "draw_two", "count": 4}
    assert len(guest.hand) == 1


@pytest.mark.parametrize("action_stack", [
    {"kind": "draw_two", "count": 3},
    {"kind": "skip", "count": 0},
    {"kind": "wild_draw_four", "count": True},
    {"kind": "unknown", "count": 2},
    {"kind": ["draw_two"], "count": 2},
    {"kind": "draw_two", "count": 2, "card_id": "private"},
])
def test_test_state_rejects_invalid_action_stack_without_mutation(monkeypatch, action_stack):
    monkeypatch.setenv("TEST_MODE", "1")
    room, host, guest = make_started_room()
    game = room.active_game
    before = (room.state_version, game.current_player_id, len(host.hand), len(guest.hand))
    with pytest.raises(CommandError) as exc_info:
        process_command(room, Command(
            "invalid-stack", room.room_id, host.player_id, "TEST_SET_STATE", {
                "current_player_id": guest.player_id,
                "discard_asset_key": "uno_red_draw_two",
                "hands": {host.player_id: [], guest.player_id: []},
                "action_stack": action_stack,
            },
        ))
    assert exc_info.value.code == "BAD_TEST_STATE"
    assert (room.state_version, game.current_player_id, len(host.hand), len(guest.hand)) == before
