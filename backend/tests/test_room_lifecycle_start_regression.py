from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.domain.cards import CardColor
from backend.app.domain.room import GameStatus, Room, RoomPhase, new_player
from backend.app.engine.command_handler import Command, CommandError, process_command
from backend.app.engine.invariants import assert_room_invariants


def make_room(player_count: int = 3):
    host = new_player("host", 0, is_host=True)
    players = [host]
    for index in range(1, player_count):
        players.append(new_player(f"p{index}", index))
    return Room(room_id="STEP1", host_player_id=host.player_id, players=players), host, players


def start_as(room: Room, player_id: str, action_id: str = "start", seed: int = 17) -> dict:
    return process_command(
        room,
        Command(
            action_id=action_id,
            room_id=room.room_id,
            player_id=player_id,
            command_type="START_GAME",
            payload={"seed": seed},
        ),
    )


def clear_api_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def collect_strings(value) -> set[str]:
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        found: set[str] = set()
        for item in value.values():
            found.update(collect_strings(item))
        return found
    if isinstance(value, list):
        found: set[str] = set()
        for item in value:
            found.update(collect_strings(item))
        return found
    return set()


def player_hand_ids(player) -> tuple[str, ...]:
    return tuple(card.card_id for card in player.hand)


def game_fingerprint(room: Room) -> dict:
    game = room.active_game
    if game is None:
        return {"phase": room.phase, "active_game": None}
    return {
        "phase": room.phase,
        "game_id": game.game_id,
        "game_epoch": game.game_epoch,
        "status": game.status,
        "hands": tuple(player_hand_ids(player) for player in room.seats_in_order()),
        "deck": tuple(card.card_id for card in game.deck),
        "discard": tuple(card.card_id for card in game.discard_pile),
        "current_player_id": game.current_player_id,
        "direction": game.direction,
        "current_color": game.current_color,
        "state_version": room.state_version,
    }


def assert_started_state_is_valid(room: Room, players) -> None:
    assert room.phase == RoomPhase.IN_GAME
    game = room.active_game
    assert game is not None
    assert game.status == GameStatus.ACTIVE
    assert [len(player.hand) for player in players] == [7] * len(players)
    assert len(game.deck) > 0
    assert len(game.discard_pile) >= 1
    player_ids = {player.player_id for player in players}
    assert len(player_ids) == len(players)
    assert {player.player_id for player in room.players} == player_ids
    assert game.current_player_id in player_ids
    assert game.direction in {-1, 1}
    assert game.current_color in set(CardColor)
    assert_room_invariants(room)


def assert_private_snapshot_does_not_expose_other_hands(room: Room, viewer) -> None:
    snapshot = main._private_snapshot(room, viewer.player_id)
    assert snapshot["event"] == "private_snapshot"
    assert all("hand" not in player for player in snapshot["state"]["players"])
    own_ids = set(player_hand_ids(viewer))
    visible_ids = {card["card_id"] for card in snapshot["you"]["hand"]}
    if visible_ids != own_ids:
        raise AssertionError("private snapshot does not match requesting player's hand")
    other_ids: set[str] = set()
    for player in room.players:
        if player.player_id != viewer.player_id:
            other_ids.update(player_hand_ids(player))
    if collect_strings(snapshot) & other_ids:
        raise AssertionError("private snapshot exposed another player's hand")


def test_host_can_start_without_ready_flags_and_deals_valid_state():
    room, host, players = make_room(3)

    result = start_as(room, host.player_id, seed=17)

    assert result["ok"] is True
    assert_started_state_is_valid(room, players)


def test_non_host_cannot_start_and_does_not_change_lobby_state():
    room, _host, players = make_room(3)
    before_version = room.state_version

    with pytest.raises(CommandError) as raised:
        start_as(room, players[1].player_id, seed=17)

    assert raised.value.code == "HOST_REQUIRED"
    assert room.phase == RoomPhase.LOBBY
    assert room.active_game is None
    assert [len(player.hand) for player in players] == [0, 0, 0]
    assert room.state_version == before_version


def test_insufficient_players_cannot_start_and_does_not_deal():
    room, host, players = make_room(1)

    with pytest.raises(CommandError) as raised:
        start_as(room, host.player_id, seed=17)

    assert raised.value.code == "INVALID_PLAYER_COUNT"
    assert room.phase == RoomPhase.LOBBY
    assert room.active_game is None
    assert [len(player.hand) for player in players] == [0]


def test_duplicate_start_has_no_side_effects():
    room, host, players = make_room(3)
    start_as(room, host.player_id, action_id="start-once", seed=17)
    before = game_fingerprint(room)

    with pytest.raises(CommandError) as raised:
        start_as(room, host.player_id, action_id="start-again", seed=29)

    assert raised.value.code == "ROOM_NOT_IN_LOBBY"
    after = game_fingerprint(room)
    if after != before:
        raise AssertionError("duplicate START_GAME changed game state")
    assert [len(player.hand) for player in players] == [7, 7, 7]


def test_start_after_host_command_has_valid_game_state():
    room, host, players = make_room(4)

    start_as(room, host.player_id, seed=23)

    assert_started_state_is_valid(room, players)


def test_private_snapshot_exposes_only_requesting_players_hand():
    room, host, players = make_room(3)
    start_as(room, host.player_id, seed=17)

    for viewer in players:
        assert_private_snapshot_does_not_expose_other_hands(room, viewer)


def test_reset_then_start_again_without_ready_flags():
    room, host, players = make_room(3)
    start_as(room, host.player_id, action_id="start-before-reset", seed=17)

    reset = process_command(
        room,
        Command(
            action_id="reset",
            room_id=room.room_id,
            player_id=host.player_id,
            command_type="RESET_ROOM",
        ),
    )
    assert reset["room_phase"] == "LOBBY"
    assert [len(player.hand) for player in players] == [0, 0, 0]
    assert [player.ready for player in players] == [False, False, False]

    result = start_as(room, host.player_id, action_id="start-after-reset", seed=31)

    assert result["ok"] is True
    assert_started_state_is_valid(room, players)


def test_websocket_snapshots_after_host_start_are_consistent_and_private():
    clear_api_rooms()
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    room_code = host["room_code"]
    guests = [
        client.post(f"/api/v1/rooms/{room_code}/join", json={"nickname": "p1"}).json(),
        client.post(f"/api/v1/rooms/{room_code}/join", json={"nickname": "p2"}).json(),
    ]

    start = client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={
            "action_id": "host-start-without-ready",
            "player_id": host["player_id"],
            "command_type": "START_GAME",
            "payload": {"seed": 17},
        },
        headers={"Authorization": f"Bearer {host['session_id']}"},
    )
    assert start.status_code == 200

    players = [host, *guests]
    with main.rooms_lock:
        room = main.rooms[room_code]
        hand_ids_by_player = {player.player_id: set(player_hand_ids(player)) for player in room.players}

    public_summaries = []
    for player in players:
        with client.websocket_connect(
            f"/api/v1/rooms/{room_code}/ws?player_id={player['player_id']}&session_id={player['session_id']}"
        ) as websocket:
            public = websocket.receive_json()
            private = websocket.receive_json()

        assert public["event"] == "snapshot"
        assert private["event"] == "private_snapshot"
        state = public["state"]
        active_game = state["active_game"]
        public_summaries.append(
            (
                state["phase"],
                active_game["game_id"],
                active_game["status"],
                active_game["current_player_id"],
                active_game["direction"],
                active_game["current_color"],
                active_game["deck_count"],
                active_game["discard_count"],
                tuple(member["hand_count"] for member in state["players"]),
            )
        )
        assert all("hand" not in member for member in private["state"]["players"])
        viewer_id = player["player_id"]
        visible_ids = {card["card_id"] for card in private["you"]["hand"]}
        if visible_ids != hand_ids_by_player[viewer_id]:
            raise AssertionError("websocket private snapshot does not match requesting player's hand")
        other_ids = set().union(
            *(ids for player_id, ids in hand_ids_by_player.items() if player_id != viewer_id)
        )
        if collect_strings(private) & other_ids:
            raise AssertionError("websocket private snapshot exposed another player's hand")

    if len(set(public_summaries)) != 1:
        raise AssertionError("websocket public snapshots are inconsistent")

    clear_api_rooms()
