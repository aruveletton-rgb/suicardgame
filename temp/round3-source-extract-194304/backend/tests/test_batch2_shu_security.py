from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main
from backend.tests.ready_helpers import ready_all_http
from backend.app.domain.cards import Card, SPECIAL_BY_KIND, build_core_uno_deck


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def auth_header(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session_id']}"}


def uno(asset_key: str):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def special(kind: str) -> Card:
    return Card.from_spec(SPECIAL_BY_KIND[kind])


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


def make_started_room(client: TestClient):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, 3):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    ready_all_http(client, host["room_code"], players)
    start = command(client, host["room_code"], host, host["player_id"], "START_GAME", {"seed": 908}, "start")
    assert start.status_code == 200
    return host["room_code"], host, players


def summary(room_code: str):
    room = main.rooms[room_code]
    game = room.active_game
    assert game is not None
    return {
        "state_version": room.state_version,
        "current_player_id": game.current_player_id,
        "deck_ids": [card.card_id for card in game.deck],
        "discard_ids": [card.card_id for card in game.discard_pile],
        "hands": {player.player_id: [card.card_id for card in player.hand] for player in room.players},
    }


def assert_unchanged(room_code: str, before) -> None:
    with main.rooms_lock:
        assert summary(room_code) == before


def configure_shu(room_code: str, players: list[dict], *, current_index: int = 0):
    host_shu = special("shu")
    guest_shu = special("shu")
    red_cards = [uno("uno_red_1"), uno("uno_red_2"), uno("uno_red_3"), uno("uno_red_4")]
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        room.player(players[0]["player_id"]).hand = [host_shu, *red_cards]
        room.player(players[1]["player_id"]).hand = [guest_shu, uno("uno_green_1")]
        room.player(players[2]["player_id"]).hand = [uno("uno_yellow_2")]
        game.current_player_id = players[current_index]["player_id"]
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_6")]
        game.current_prompt = None
        game.effect_queue = []
        before = summary(room_code)
    return host_shu, guest_shu, before


def test_batch2_http_missing_session_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _guest_shu, before = configure_shu(room_code, players)

    response = command(client, room_code, None, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": shu.card_id, "chosen_color": "red"}, "shu-missing-session")

    assert response.status_code in {401, 403}
    assert_unchanged(room_code, before)
    clear_rooms()


def test_batch2_http_invalid_session_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _guest_shu, before = configure_shu(room_code, players)

    response = command(client, room_code, {**host, "session_id": "invalid-session"}, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": shu.card_id, "chosen_color": "red"}, "shu-invalid-session")

    assert response.status_code in {401, 403}
    assert_unchanged(room_code, before)
    clear_rooms()


def test_shu_reject_non_current_player():
    clear_rooms()
    client = TestClient(main.app)
    room_code, _host, players = make_started_room(client)
    _host_shu, guest_shu, before = configure_shu(room_code, players)
    guest = players[1]

    response = command(client, room_code, guest, guest["player_id"], "ACTIVATE_SPECIAL", {"card_id": guest_shu.card_id, "chosen_color": "red"}, "shu-non-current")

    assert response.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_shu_reject_player_id_spoof():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _guest_shu, before = configure_shu(room_code, players)
    guest = players[1]

    response = command(client, room_code, guest, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": shu.card_id, "chosen_color": "red"}, "shu-spoof")

    assert response.status_code in {401, 403}
    assert_unchanged(room_code, before)
    clear_rooms()


def test_batch2_ws_invalid_identity_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _guest_shu, before = configure_shu(room_code, players)
    guest = players[1]

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={guest['player_id']}&session_id={guest['session_id']}") as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        websocket.send_json(
            {
                "event": "command",
                "action_id": "shu-ws-spoof",
                "player_id": host["player_id"],
                "command_type": "ACTIVATE_SPECIAL",
                "payload": {"card_id": shu.card_id, "chosen_color": "red"},
            }
        )
        error = websocket.receive_json()
        assert error["event"] == "error"
        assert error["error"] == "AUTH_PLAYER_MISMATCH"
        assert_unchanged(room_code, before)
    clear_rooms()


def test_shu_duplicate_action_id_no_double_apply():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _guest_shu, before = configure_shu(room_code, players)

    first = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "shu-repeat",
        expected_state_version=before["state_version"],
    )
    after_first = summary(room_code)
    replay = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "shu-repeat",
        expected_state_version=before["state_version"],
    )

    assert first.status_code == 200
    assert replay.status_code == 200
    assert summary(room_code) == after_first
    clear_rooms()


def test_shu_stale_expected_state_version_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    shu, _guest_shu, before = configure_shu(room_code, players)

    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": shu.card_id, "chosen_color": "red"},
        "shu-stale",
        expected_state_version=before["state_version"] - 1,
    )

    assert response.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()
