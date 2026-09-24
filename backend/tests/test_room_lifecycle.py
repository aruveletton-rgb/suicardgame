import pytest

from backend.app.domain.room import Room, RoomPhase, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command


def make_room(player_count=2):
    host = new_player("host", 0, is_host=True)
    players = [host]
    for index in range(1, player_count):
        players.append(new_player(f"p{index}", index))
    return Room(room_id="ABC123", host_player_id=host.player_id, players=players), host, players


def ready_all(room):
    for player in room.players:
        process_command(room, Command(action_id=f"ready-{player.player_id}", room_id=room.room_id, player_id=player.player_id, command_type="READY"))


def test_start_game_deals_seven_cards_and_real_shop_goods():
    room, host, players = make_room(4)
    ready_all(room)
    result = process_command(room, Command(action_id="start-1", room_id=room.room_id, player_id=host.player_id, command_type="START_GAME", payload={"seed": 7}))
    assert result["ok"] is True
    assert room.phase == RoomPhase.IN_GAME
    assert all(len(player.hand) == 7 for player in players)
    assert room.active_game is not None
    assert len(room.active_game.shop.goods) == 8
    assert room.active_game.shop.field_card.kind == "cannot"


def test_host_can_start_without_waiting_for_ready_flags():
    room, host, players = make_room(3)
    result = process_command(
        room,
        Command(
            action_id="start-without-ready",
            room_id=room.room_id,
            player_id=host.player_id,
            command_type="START_GAME",
            payload={"seed": 17},
        ),
    )
    assert result["ok"] is True
    assert room.phase == RoomPhase.IN_GAME
    assert all(len(player.hand) == 7 for player in players)


def test_reset_aborts_game_and_returns_clean_lobby():
    room, host, players = make_room(2)
    ready_all(room)
    process_command(room, Command(action_id="start-1", room_id=room.room_id, player_id=host.player_id, command_type="START_GAME", payload={"seed": 11}))
    game_id = room.active_game.game_id
    game_epoch = room.active_game.game_epoch

    result = process_command(room, Command(action_id="reset-1", room_id=room.room_id, player_id=host.player_id, command_type="RESET_ROOM"))
    assert result["room_phase"] == "LOBBY"
    assert room.active_game is None
    assert all(not player.hand and not player.ready for player in players)
    assert room.game_history[-1]["game_id"] == game_id

    with pytest.raises(CommandError) as raised:
        process_command(
            room,
            Command(
                action_id="old-play",
                room_id=room.room_id,
                player_id=host.player_id,
                command_type="PLAY_CARD",
                game_id=game_id,
                game_epoch=game_epoch,
                payload={"card_id": "missing"},
            ),
        )
    assert raised.value.code == "STALE_GAME_COMMAND"


def test_action_id_is_idempotent():
    room, host, _ = make_room(2)
    first = process_command(room, Command(action_id="same", room_id=room.room_id, player_id=host.player_id, command_type="READY"))
    second = process_command(room, Command(action_id="same", room_id=room.room_id, player_id=host.player_id, command_type="READY", payload={"ready": False}))
    assert first == second
    assert host.ready is True
