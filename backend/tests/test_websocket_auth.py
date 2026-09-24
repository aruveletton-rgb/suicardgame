from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import backend.app.main as main
from backend.app.domain.cards import build_core_uno_deck


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def auth_header(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_id']}"}


def card(asset_key: str):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def command(client: TestClient, room_code: str, session: dict, player_id: str, command_type: str, payload=None, action_id="cmd"):
    return client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={"action_id": action_id, "player_id": player_id, "command_type": command_type, "payload": payload or {}},
        headers=auth_header(session),
    )


def make_room(client: TestClient, player_count: int = 3):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, player_count):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    return host["room_code"], host, players


def make_started_room(client: TestClient):
    room_code, host, players = make_room(client, 3)
    response = command(client, room_code, host, host["player_id"], "START_GAME", {"seed": 501}, "start")
    assert response.status_code == 200
    return room_code, host, players


def assert_ws_rejected(client: TestClient, url: str) -> None:
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url) as websocket:
            websocket.receive_json()


def test_websocket_missing_session_is_rejected_without_private_snapshot():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_room(client, 3)

    assert_ws_rejected(client, f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}")
    clear_rooms()


def test_websocket_invalid_session_is_rejected_without_private_snapshot():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_room(client, 3)

    assert_ws_rejected(client, f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id=invalid-session")
    clear_rooms()


def test_websocket_player_id_session_mismatch_is_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_room(client, 3)
    guest = players[1]

    assert_ws_rejected(client, f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id={guest['session_id']}")
    clear_rooms()


def test_websocket_valid_session_receives_private_snapshot_scoped_to_player():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client)

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id={host['session_id']}") as websocket:
        public = websocket.receive_json()
        private = websocket.receive_json()

    assert public["event"] == "snapshot"
    assert private["event"] == "private_snapshot"
    assert private["you"]["player_id"] == host["player_id"]
    assert all("hand" not in player for player in private["state"]["players"])
    clear_rooms()


def test_websocket_command_rejects_spoofed_host_player_id():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_room(client, 3)
    guest = players[1]

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={guest['player_id']}&session_id={guest['session_id']}") as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        websocket.send_json(
            {
                "event": "command",
                "action_id": "guest-spoof-start",
                "player_id": host["player_id"],
                "command_type": "START_GAME",
                "payload": {"seed": 502},
            }
        )
        error = websocket.receive_json()

    assert error["event"] == "error"
    assert error["error"] in {"AUTH_PLAYER_MISMATCH", "HOST_REQUIRED"}
    with main.rooms_lock:
        assert main.rooms[room_code].phase.value == "LOBBY"
    clear_rooms()


def test_websocket_non_current_player_cannot_spoof_play_or_draw():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        current = room.player(game.current_player_id)
        current.hand = [card("uno_red_7"), card("uno_blue_9")]
        game.discard_pile = [card("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [card("uno_green_1")]
        before = (len(current.hand), len(game.deck), len(game.discard_pile), game.current_player_id)

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={guest['player_id']}&session_id={guest['session_id']}") as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        websocket.send_json(
            {
                "event": "command",
                "action_id": "guest-spoof-play",
                "player_id": current.player_id,
                "command_type": "PLAY_CARD",
                "payload": {"card_id": current.hand[0].card_id},
            }
        )
        play_error = websocket.receive_json()
        websocket.send_json(
            {
                "event": "command",
                "action_id": "guest-spoof-draw",
                "player_id": current.player_id,
                "command_type": "DRAW_CARD",
                "payload": {},
            }
        )
        draw_error = websocket.receive_json()

    assert play_error["event"] == "error"
    assert draw_error["event"] == "error"
    assert play_error["error"] == "AUTH_PLAYER_MISMATCH"
    assert draw_error["error"] == "AUTH_PLAYER_MISMATCH"
    with main.rooms_lock:
        game = main.rooms[room_code].active_game
        current = main.rooms[room_code].player(game.current_player_id)
        assert before == (len(current.hand), len(game.deck), len(game.discard_pile), game.current_player_id)
    clear_rooms()
