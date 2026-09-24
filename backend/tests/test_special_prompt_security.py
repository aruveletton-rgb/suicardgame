from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main
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


def make_started_room(client: TestClient, player_count: int = 3):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, player_count):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    start = command(client, host["room_code"], host, host["player_id"], "START_GAME", {"seed": 702}, "start")
    assert start.status_code == 200
    return host["room_code"], host, players


def open_ji_prompt(client: TestClient, room_code: str, host: dict):
    ji = special("ji")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        host_player = room.player(host["player_id"])
        host_player.hand = [ji]
        game.current_player_id = host_player.player_id
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4")]
        game.current_prompt = None
        game.effect_queue = []
    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ji.card_id, "chosen_color": "red"}, "open-ji")
    assert response.status_code == 200
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None and game.current_prompt is not None
        return game.current_prompt.prompt_id


def prompt_snapshot(room_code: str):
    room = main.rooms[room_code]
    game = room.active_game
    return {
        "phase": room.phase.value,
        "state_version": room.state_version,
        "current_player_id": game.current_player_id if game else None,
        "prompt_id": game.current_prompt.prompt_id if game and game.current_prompt else None,
        "responder_ids": list(game.current_prompt.responder_ids) if game and game.current_prompt else [],
        "effect_queue": list(game.effect_queue) if game else [],
    }


def assert_prompt_unchanged(room_code: str, before) -> None:
    with main.rooms_lock:
        assert prompt_snapshot(room_code) == before


def test_respond_to_prompt_rejects_non_responder_and_body_player_id_spoof():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    first_prompt_id = open_ji_prompt(client, room_code, host)
    responder = players[1]
    non_responder = players[2]
    before = prompt_snapshot(room_code)

    wrong_player = command(
        client,
        room_code,
        non_responder,
        non_responder["player_id"],
        "RESPOND_TO_PROMPT",
        {"prompt_id": first_prompt_id, "response": "pass"},
        "non-responder",
    )
    spoof_responder = command(
        client,
        room_code,
        non_responder,
        responder["player_id"],
        "RESPOND_TO_PROMPT",
        {"prompt_id": first_prompt_id, "response": "pass"},
        "spoof-responder",
    )

    assert wrong_player.status_code == 400
    assert spoof_responder.status_code in {401, 403}
    assert_prompt_unchanged(room_code, before)
    clear_rooms()


def test_respond_to_prompt_rejects_invalid_and_already_advanced_prompt_ids():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    first_prompt_id = open_ji_prompt(client, room_code, host)
    responder = players[1]

    invalid = command(
        client,
        room_code,
        responder,
        responder["player_id"],
        "RESPOND_TO_PROMPT",
        {"prompt_id": "missing-prompt", "response": "pass"},
        "invalid-prompt",
    )
    before_valid = prompt_snapshot(room_code)
    accepted = command(
        client,
        room_code,
        responder,
        responder["player_id"],
        "RESPOND_TO_PROMPT",
        {"prompt_id": first_prompt_id, "response": "pass"},
        "first-response",
    )
    after_first = prompt_snapshot(room_code)
    replay = command(
        client,
        room_code,
        responder,
        responder["player_id"],
        "RESPOND_TO_PROMPT",
        {"prompt_id": first_prompt_id, "response": "pass"},
        "first-response",
    )
    stale_prompt = command(
        client,
        room_code,
        responder,
        responder["player_id"],
        "RESPOND_TO_PROMPT",
        {"prompt_id": first_prompt_id, "response": "pass"},
        "old-prompt-new-action",
    )

    assert invalid.status_code == 400
    assert accepted.status_code == 200
    assert replay.status_code == 200
    assert stale_prompt.status_code == 400
    assert before_valid["prompt_id"] == first_prompt_id
    assert after_first["prompt_id"] != first_prompt_id
    assert_prompt_unchanged(room_code, after_first)
    clear_rooms()


def test_reset_invalidates_old_special_prompt():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    old_prompt_id = open_ji_prompt(client, room_code, host)
    responder = players[1]

    reset = command(client, room_code, host, host["player_id"], "RESET_ROOM", {}, "reset-room")
    response = command(
        client,
        room_code,
        responder,
        responder["player_id"],
        "RESPOND_TO_PROMPT",
        {"prompt_id": old_prompt_id, "response": "pass"},
        "respond-after-reset",
    )

    assert reset.status_code == 200
    assert response.status_code == 400
    with main.rooms_lock:
        room = main.rooms[room_code]
        assert room.phase.value == "LOBBY"
        assert room.active_game is None
    clear_rooms()


def test_websocket_prompt_commands_remain_bound_to_authenticated_player():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    prompt_id = open_ji_prompt(client, room_code, host)
    responder = players[1]
    non_responder = players[2]
    before = prompt_snapshot(room_code)

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={non_responder['player_id']}&session_id={non_responder['session_id']}") as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        websocket.send_json(
            {
                "event": "command",
                "action_id": "ws-spoof-responder",
                "player_id": responder["player_id"],
                "command_type": "RESPOND_TO_PROMPT",
                "payload": {"prompt_id": prompt_id, "response": "pass"},
            }
        )
        spoof_error = websocket.receive_json()
        websocket.send_json(
            {
                "event": "command",
                "action_id": "ws-non-responder",
                "player_id": non_responder["player_id"],
                "command_type": "RESPOND_TO_PROMPT",
                "payload": {"prompt_id": prompt_id, "response": "pass"},
            }
        )
        non_responder_error = websocket.receive_json()
        assert spoof_error["event"] == "error"
        assert spoof_error["error"] == "AUTH_PLAYER_MISMATCH"
        assert non_responder_error["event"] == "error"
        assert non_responder_error["error"] == "NOT_PROMPT_RESPONDER"
        assert_prompt_unchanged(room_code, before)

    clear_rooms()
