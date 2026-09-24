from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.domain.cards import build_core_uno_deck


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def auth_header(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_id']}"}


def card(asset_key: str):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def command(client: TestClient, room_code: str, session: dict, player_id: str, command_type: str, payload=None, action_id="cmd", expected_state_version=None):
    body = {
        "action_id": action_id,
        "player_id": player_id,
        "command_type": command_type,
        "payload": payload or {},
    }
    if expected_state_version is not None:
        body["expected_state_version"] = expected_state_version
    return client.post(f"/api/v1/rooms/{room_code}/commands", json=body, headers=auth_header(session))


def make_room(client: TestClient, player_count: int = 3):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, player_count):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    return host["room_code"], host, players


def make_started_room(client: TestClient):
    room_code, host, players = make_room(client, 3)
    response = command(client, room_code, host, host["player_id"], "START_GAME", {"seed": 601}, "start")
    assert response.status_code == 200
    return room_code, host, players


def test_reconnect_token_is_bound_to_exact_player_and_private_snapshot_scope():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]

    wrong_player = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": guest["player_id"], "reconnect_token": host["reconnect_token"]},
    )
    assert wrong_player.status_code == 403

    wrong_token = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": host["player_id"], "reconnect_token": "invalid-token"},
    )
    assert wrong_token.status_code == 403

    restored = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": host["player_id"], "reconnect_token": host["reconnect_token"]},
    )
    assert restored.status_code == 200
    body = restored.json()
    assert body["player_id"] == host["player_id"]
    assert body["reconnect_token"] != host["reconnect_token"]
    assert body["private_snapshot"]["you"]["player_id"] == host["player_id"]
    assert all("hand" not in player for player in body["private_snapshot"]["state"]["players"])
    clear_rooms()


def test_duplicate_action_id_does_not_double_apply_start_draw_or_play():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_room(client, 3)

    first_start = command(client, room_code, host, host["player_id"], "START_GAME", {"seed": 602}, "same-start")
    second_start = command(client, room_code, host, host["player_id"], "START_GAME", {"seed": 999}, "same-start")
    assert first_start.status_code == 200
    assert second_start.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        start_fingerprint = (game.game_id, tuple(len(player.hand) for player in room.players), len(game.deck), len(game.discard_pile))
        current = room.player(game.current_player_id)
        current.hand = [card("uno_red_7"), card("uno_blue_9")]
        game.discard_pile = [card("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [card("uno_green_1"), card("uno_yellow_2")]
        draw_player_id = current.player_id

    first_draw = command(client, room_code, host, draw_player_id, "DRAW_CARD", {}, "same-draw")
    second_draw = command(client, room_code, host, draw_player_id, "DRAW_CARD", {}, "same-draw")
    assert first_draw.status_code == 200
    assert second_draw.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert start_fingerprint[0] == game.game_id
        assert len(game.deck) == 1
        current = room.player(draw_player_id)
        current.hand = [card("uno_red_7"), card("uno_blue_9")]
        game.current_player_id = current.player_id
        game.discard_pile = [card("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [card("uno_green_1")]
        played_id = current.hand[0].card_id

    first_play = command(client, room_code, host, draw_player_id, "PLAY_CARD", {"card_id": played_id}, "same-play")
    second_play = command(client, room_code, host, draw_player_id, "PLAY_CARD", {"card_id": played_id}, "same-play")
    assert first_play.status_code == 200
    assert second_play.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert len(room.player(draw_player_id).hand) == 1
        assert len(game.discard_pile) == 2
    clear_rooms()


def test_stale_expected_state_version_is_rejected_without_mutation():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_room(client, 3)
    with main.rooms_lock:
        room = main.rooms[room_code]
        current_version = room.state_version
    assert current_version > 0

    stale = command(
        client,
        room_code,
        host,
        host["player_id"],
        "READY",
        {"ready": True},
        "stale-ready",
        expected_state_version=current_version - 1,
    )

    assert stale.status_code == 400
    with main.rooms_lock:
        room = main.rooms[room_code]
        assert room.player(host["player_id"]).ready is False
    clear_rooms()
