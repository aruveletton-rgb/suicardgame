from __future__ import annotations

import asyncio
from dataclasses import replace
from time import time

import pytest

import backend.app.main as main
from backend.app.domain.cards import Card, CardColor, iter_uno_specs
from backend.app.domain.room import Prompt, PromptKind, PromptResolutionPolicy, PromptStatus, Room, RoomPhase, new_player
from backend.app.engine.command_handler import Command, pause_expired_step, process_command
from backend.app.repositories.json_store import JsonSnapshotStore


def card(asset_key: str) -> Card:
    return Card.from_spec(next(spec for spec in iter_uno_specs() if spec.asset_key == asset_key))


def command(room: Room, player_id: str, action_id: str, kind: str, payload: dict | None = None):
    return process_command(room, Command(action_id, room.room_id, player_id, kind, payload or {}))


def start(room: Room, prefix: str = "initial") -> None:
    for player in room.players:
        command(room, player.player_id, f"{prefix}:ready:{player.seat_index}", "READY", {"ready": True})
    command(room, room.host_player_id, f"{prefix}:start", "START_GAME", {"seed": 17})


def set_bot_turn(room: Room) -> None:
    game = room.active_game
    assert game is not None
    room.players[0].hand = [card("uno_yellow_6"), card("uno_green_8")]
    room.players[1].hand = [card("uno_blue_1"), card("uno_yellow_9"), card("uno_green_7")]
    game.current_player_id = room.players[1].player_id
    game.discard_pile = [card("uno_blue_2")]
    game.current_color = CardColor.BLUE
    game.current_prompt = None
    game.effect_queue = []
    game.deck = [card("uno_red_3"), card("uno_blue_5")]


def bot_room(room_id: str = "DELAY1") -> Room:
    host = new_player("host", 0, is_host=True)
    bot = new_player("bot", 1, is_bot=True)
    room = Room(room_id, host.player_id, [host, bot])
    for player in room.players:
        player.session_id = "test-only-session"
        player.reconnect_token = "test-only-reconnect"
    start(room)
    set_bot_turn(room)
    return room


def response_window(room: Room, prompt_id: str = "delayed-response") -> Prompt:
    game = room.active_game
    assert game is not None
    prompt = Prompt(
        prompt_id=prompt_id,
        kind=PromptKind.GENERIC_RESPONSE_WINDOW,
        source_player_id=room.host_player_id,
        source_card_id=None,
        responder_ids=[room.players[1].player_id],
        legal_responses=["pass"],
        created_at=time(),
        deadline_at=time() + 30,
        default_action="pass",
        state_version=room.state_version,
        resolution_policy=PromptResolutionPolicy.FIRST_WINS,
        game_id=game.game_id,
        game_epoch=game.game_epoch,
    )
    game.current_prompt = prompt
    game.turn_deadline_at = None
    return prompt


@pytest.fixture
def bot_runtime(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "rooms", {})
    monkeypatch.setattr(main, "snapshot_store", JsonSnapshotStore(tmp_path / "rooms"))
    monkeypatch.setattr(main, "websocket_hub", main.WebSocketHub())
    monkeypatch.setattr(main, "_schedule_prompt_expiry", lambda room: None)


def run_ticks(monkeypatch, ticks) -> None:
    clock = [0.0]
    iterator = iter(ticks)

    async def poll(_delay):
        try:
            tick = next(iterator)
        except StopIteration:
            raise asyncio.CancelledError
        if isinstance(tick, tuple):
            clock[0], before_poll = tick
            before_poll()
        else:
            clock[0] = tick

    monkeypatch.setattr(main, "monotonic", lambda: clock[0], raising=False)
    monkeypatch.setattr(main.asyncio, "sleep", poll)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._bot_loop())


def test_normal_bot_turn_waits_before_play_and_persists(monkeypatch, bot_runtime):
    room = bot_room()
    bot = room.players[1]
    main.rooms[room.room_id] = room

    def still_waiting():
        assert len(bot.hand) == 3
        assert room.active_game.current_player_id == bot.player_id
        assert not main.snapshot_store.path_for_room(room.room_id).exists()

    run_ticks(monkeypatch, [0.0, (1.49, still_waiting), 1.5])

    assert len(bot.hand) == 2
    assert room.active_game.current_player_id == room.host_player_id
    saved = main.snapshot_store.load_room_snapshots()[0]
    assert saved.state_version == room.state_version
    assert len(saved.players[1].hand) == 2


def test_bot_response_window_waits_before_resolving(monkeypatch, bot_runtime):
    room = bot_room()
    prompt = response_window(room)
    main.rooms[room.room_id] = room

    def still_waiting():
        assert room.active_game.current_prompt is prompt
        assert prompt.response_records == {}

    run_ticks(monkeypatch, [0.0, (1.49, still_waiting), 1.5])

    assert room.active_game.current_prompt is None
    assert prompt.status == PromptStatus.RESOLVED
    assert prompt.response_records == {room.players[1].player_id: "pass"}


def test_each_consecutive_bot_draw_waits_again(monkeypatch, bot_runtime):
    room = bot_room()
    game = room.active_game
    bot = room.players[1]
    bot.hand = [card("uno_yellow_9")]
    game.deck = [card("uno_blue_5"), card("uno_green_7"), card("uno_red_3")]
    main.rooms[room.room_id] = room

    def has_only_first_draw():
        assert [item.asset_key for item in bot.hand] == ["uno_yellow_9", "uno_red_3"]
        assert game.current_player_id == bot.player_id

    run_ticks(monkeypatch, [0.0, 1.5, (2.99, has_only_first_draw), 3.0, 4.5])

    assert [item.asset_key for item in bot.hand] == [
        "uno_yellow_9", "uno_red_3", "uno_green_7", "uno_blue_5",
    ]
    assert game.current_player_id == bot.player_id
    assert room.phase == RoomPhase.IN_GAME


@pytest.mark.parametrize("change", ["pause", "reset", "close"])
def test_pending_action_is_cancelled_when_game_stops(monkeypatch, bot_runtime, change):
    room = bot_room()
    main.rooms[room.room_id] = room

    def stop_game():
        assert len(room.players[1].hand) == 3
        if change == "pause":
            assert pause_expired_step(room, prompt_id=None, now=room.active_game.turn_deadline_at)
        else:
            kind = "RESET_ROOM" if change == "reset" else "CLOSE_ROOM"
            command(room, room.host_player_id, "stop", kind)

    run_ticks(monkeypatch, [0.0, (1.0, stop_game), 1.5, 4.0])

    assert not main.snapshot_store.path_for_room(room.room_id).exists()
    if change == "pause":
        assert len(room.players[1].hand) == 3
        assert room.active_game.pause_state is not None
    elif change == "reset":
        assert room.active_game is None
        assert room.phase == RoomPhase.LOBBY
    else:
        assert room.phase == RoomPhase.CLOSED


def test_new_game_receives_a_new_delay(monkeypatch, bot_runtime):
    room = bot_room()
    main.rooms[room.room_id] = room
    old_game_id = room.active_game.game_id

    def restart():
        assert len(room.players[1].hand) == 3
        command(room, room.host_player_id, "reset", "RESET_ROOM")
        start(room, prefix="restart")
        set_bot_turn(room)

    def still_waiting():
        assert room.active_game.game_id != old_game_id
        assert len(room.players[1].hand) == 3

    run_ticks(monkeypatch, [0.0, (1.0, restart), (1.5, still_waiting), 2.5])

    assert len(room.players[1].hand) == 2
    assert room.active_game.current_player_id == room.host_player_id


def test_replaced_response_window_receives_a_new_delay(monkeypatch, bot_runtime):
    room = bot_room()
    original = response_window(room)
    main.rooms[room.room_id] = room

    def replace_window():
        assert original.response_records == {}
        room.active_game.current_prompt = replace(original, prompt_id="replacement-window", response_records={})

    def still_waiting():
        assert room.active_game.current_prompt.prompt_id == "replacement-window"
        assert room.active_game.current_prompt.response_records == {}

    run_ticks(monkeypatch, [0.0, (1.0, replace_window), (1.5, still_waiting), 2.5])

    assert room.active_game.current_prompt is None
    assert room.active_game.last_prompt.prompt_id == "replacement-window"
    assert original.response_records == {}


def test_waiting_rooms_do_not_delay_each_other(monkeypatch, bot_runtime):
    first = bot_room("DELAY1")
    second = bot_room("DELAY2")
    main.rooms[first.room_id] = first

    def add_second_room():
        assert len(first.players[1].hand) == 3
        main.rooms[second.room_id] = second

    def first_has_acted():
        assert len(first.players[1].hand) == 2
        assert len(second.players[1].hand) == 3

    run_ticks(monkeypatch, [0.0, (1.0, add_second_room), 1.5, (2.49, first_has_acted), 2.5])

    assert len(first.players[1].hand) == 2
    assert len(second.players[1].hand) == 2
    assert first.active_game.current_player_id == first.host_player_id
    assert second.active_game.current_player_id == second.host_player_id
