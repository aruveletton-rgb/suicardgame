from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.domain.cards import build_core_uno_deck
from backend.tests.ready_helpers import ready_all_http


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def auth_header(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_id']}"}


def card(asset_key: str):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def command(client: TestClient, room_code: str, session: dict | None, player_id: str, command_type: str, payload=None, action_id="cmd", expected_state_version=None):
    body = {
        "action_id": action_id,
        "player_id": player_id,
        "command_type": command_type,
        "payload": payload or {},
    }
    if expected_state_version is not None:
        body["expected_state_version"] = expected_state_version
    headers = auth_header(session) if session is not None else None
    return client.post(f"/api/v1/rooms/{room_code}/commands", json=body, headers=headers)


def make_room(client: TestClient, player_count: int = 3):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, player_count):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    return host["room_code"], host, players


def make_started_room(client: TestClient):
    room_code, host, players = make_room(client, 3)
    ready_all_http(client, room_code, players)
    response = command(client, room_code, host, host["player_id"], "START_GAME", {"seed": 401}, "start")
    assert response.status_code == 200
    return room_code, host, players


def test_http_command_missing_session_is_rejected_without_side_effects():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_room(client, 3)

    start = command(client, room_code, None, host["player_id"], "START_GAME", {"seed": 402}, "missing-start")

    assert start.status_code in {401, 403}
    with main.rooms_lock:
        assert main.rooms[room_code].phase.value == "LOBBY"

    started_code, started_host, _started_players = make_started_room(client)
    with main.rooms_lock:
        room = main.rooms[started_code]
        game = room.active_game
        assert game is not None
        current = room.player(game.current_player_id)
        current.hand = [card("uno_red_7"), card("uno_blue_9")]
        game.discard_pile = [card("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [card("uno_green_1")]
        before = (len(current.hand), len(game.deck), len(game.discard_pile), game.current_player_id)

    play = command(client, started_code, None, current.player_id, "PLAY_CARD", {"card_id": current.hand[0].card_id}, "missing-play")
    draw = command(client, started_code, None, current.player_id, "DRAW_CARD", {}, "missing-draw")

    assert play.status_code in {401, 403}
    assert draw.status_code in {401, 403}
    with main.rooms_lock:
        game = main.rooms[started_code].active_game
        current = main.rooms[started_code].player(game.current_player_id)
        assert before == (len(current.hand), len(game.deck), len(game.discard_pile), game.current_player_id)
    clear_rooms()


def test_http_command_invalid_session_is_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_room(client, 3)
    wrong_session = {**host, "session_id": "invalid-session"}

    response = command(client, room_code, wrong_session, host["player_id"], "START_GAME", {"seed": 403}, "invalid-start")

    assert response.status_code in {401, 403}
    with main.rooms_lock:
        assert main.rooms[room_code].phase.value == "LOBBY"
    clear_rooms()


def test_http_command_rejects_player_id_spoof_with_other_players_session():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_room(client, 3)
    guest = players[1]

    response = command(client, room_code, guest, host["player_id"], "START_GAME", {"seed": 404}, "guest-spoofs-host")

    assert response.status_code in {401, 403}
    with main.rooms_lock:
        assert main.rooms[room_code].phase.value == "LOBBY"
    clear_rooms()


def test_http_host_only_commands_are_bound_to_authenticated_player():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_room(client, 3)

    ready_all_http(client, room_code, players)
    start = command(client, room_code, host, host["player_id"], "START_GAME", {"seed": 405}, "host-start")
    assert start.status_code == 200

    guest = players[1]
    reset = command(client, room_code, guest, guest["player_id"], "RESET_ROOM", {}, "guest-reset")
    spoofed_reset = command(client, room_code, guest, host["player_id"], "RESET_ROOM", {}, "guest-spoof-reset")

    assert reset.status_code == 400
    assert spoofed_reset.status_code in {401, 403}
    with main.rooms_lock:
        assert main.rooms[room_code].phase.value == "IN_GAME"
    clear_rooms()


def test_http_current_player_actions_are_bound_to_authenticated_player():
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
        guest_player = room.player(guest["player_id"])
        guest_player.hand = [card("uno_red_9")]
        game.discard_pile = [card("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [card("uno_green_1")]
        before = (len(current.hand), len(guest_player.hand), len(game.deck), len(game.discard_pile), game.current_player_id)

    own_identity = command(client, room_code, guest, guest["player_id"], "PLAY_CARD", {"card_id": guest_player.hand[0].card_id}, "guest-play")
    spoof_identity = command(client, room_code, guest, current.player_id, "PLAY_CARD", {"card_id": current.hand[0].card_id}, "guest-spoof-play")
    spoof_draw = command(client, room_code, guest, current.player_id, "DRAW_CARD", {}, "guest-spoof-draw")

    assert own_identity.status_code == 400
    assert spoof_identity.status_code in {401, 403}
    assert spoof_draw.status_code in {401, 403}
    with main.rooms_lock:
        game = main.rooms[room_code].active_game
        current = main.rooms[room_code].player(game.current_player_id)
        guest_player = main.rooms[room_code].player(guest["player_id"])
        assert before == (len(current.hand), len(guest_player.hand), len(game.deck), len(game.discard_pile), game.current_player_id)
    clear_rooms()


def test_http_command_body_player_id_is_not_trusted():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_room(client, 3)
    guest = players[1]

    response = command(client, room_code, host, guest["player_id"], "READY", {"ready": True}, "host-spoofs-guest-ready")

    assert response.status_code in {401, 403}
    with main.rooms_lock:
        assert main.rooms[room_code].player(guest["player_id"]).ready is False
    clear_rooms()
