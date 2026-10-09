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
    start = command(client, host["room_code"], host, host["player_id"], "START_GAME", {"seed": 807}, "start")
    assert start.status_code == 200
    return host["room_code"], host, players


def summary(room_code: str):
    room = main.rooms[room_code]
    game = room.active_game
    assert game is not None
    return {
        "state_version": room.state_version,
        "current_player_id": game.current_player_id,
        "deck_count": len(game.deck),
        "discard_count": len(game.discard_pile),
        "hands": {player.player_id: [card.card_id for card in player.hand] for player in room.players},
    }


def assert_unchanged(room_code: str, before) -> None:
    with main.rooms_lock:
        assert summary(room_code) == before


def configure_yi(room_code: str, players: list[dict], *, current_index: int = 0):
    yi = special("yi")
    three = uno("uno_red_3")
    five = uno("uno_blue_5")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        room.player(players[0]["player_id"]).hand = [yi, three, five, uno("uno_yellow_9")]
        room.player(players[1]["player_id"]).hand = [special("yi"), uno("uno_red_1"), uno("uno_blue_7")]
        room.player(players[2]["player_id"]).hand = [uno("uno_green_1")]
        game.current_player_id = players[current_index]["player_id"]
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4"), uno("uno_blue_6")]
        game.current_prompt = None
        game.effect_queue = []
        before = summary(room_code)
    return yi, [three, five], before


def configure_ling(room_code: str, players: list[dict], *, current_index: int = 0):
    ling = special("ling")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        room.player(players[0]["player_id"]).hand = [ling, uno("uno_red_1")]
        room.player(players[1]["player_id"]).hand = [special("ling"), uno("uno_red_2"), uno("uno_blue_3"), uno("uno_green_4")]
        room.player(players[2]["player_id"]).hand = [uno("uno_green_1")]
        game.current_player_id = players[current_index]["player_id"]
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4"), uno("uno_blue_6"), uno("uno_yellow_7")]
        game.current_prompt = None
        game.effect_queue = []
        before = summary(room_code)
    return ling, before


def test_batch1_http_missing_and_invalid_session_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    yi, support, before = configure_yi(room_code, players)
    payload = {"card_id": yi.card_id, "pair_card_ids": [card.card_id for card in support]}

    missing = command(client, room_code, None, host["player_id"], "ACTIVATE_SPECIAL", payload, "yi-missing")
    invalid = command(client, room_code, {**host, "session_id": "invalid-session"}, host["player_id"], "ACTIVATE_SPECIAL", payload, "yi-invalid")

    assert missing.status_code in {401, 403}
    assert invalid.status_code in {401, 403}
    assert_unchanged(room_code, before)
    clear_rooms()


def test_yi_reject_non_current_player_and_player_id_spoof():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    yi, support, before = configure_yi(room_code, players)
    guest = players[1]

    spoof = command(client, room_code, guest, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": yi.card_id, "pair_card_ids": [card.card_id for card in support]}, "yi-spoof")
    non_current = command(client, room_code, guest, guest["player_id"], "ACTIVATE_SPECIAL", {"card_id": before["hands"][guest["player_id"]][0], "pair_card_ids": before["hands"][guest["player_id"]][1:]}, "yi-non-current")

    assert spoof.status_code in {401, 403}
    assert non_current.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_ling_reject_non_current_player_and_player_id_spoof():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    ling, before = configure_ling(room_code, players)
    guest = players[1]

    spoof = command(client, room_code, guest, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling.card_id}, "ling-spoof")
    non_current = command(client, room_code, guest, guest["player_id"], "ACTIVATE_SPECIAL", {"card_id": before["hands"][guest["player_id"]][0]}, "ling-non-current")

    assert spoof.status_code in {401, 403}
    assert non_current.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_batch1_ws_invalid_identity_rejected_without_mutation():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]
    yi, support, before = configure_yi(room_code, players)

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={guest['player_id']}&session_id={guest['session_id']}") as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        websocket.send_json(
            {
                "event": "command",
                "action_id": "batch1-ws-spoof",
                "player_id": host["player_id"],
                "command_type": "ACTIVATE_SPECIAL",
                "payload": {"card_id": yi.card_id, "pair_card_ids": [card.card_id for card in support]},
            }
        )
        error = websocket.receive_json()
        assert error["event"] == "error"
        assert error["error"] == "AUTH_PLAYER_MISMATCH"
        assert_unchanged(room_code, before)
    clear_rooms()


def test_yi_duplicate_action_id_no_double_apply_and_stale_version_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    yi, support, before = configure_yi(room_code, players)
    payload = {"card_id": yi.card_id, "pair_card_ids": [card.card_id for card in support]}

    first = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", payload, "yi-repeat", expected_state_version=before["state_version"])
    after_first = summary(room_code)
    replay = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", payload, "yi-repeat", expected_state_version=before["state_version"])

    assert first.status_code == 200
    assert replay.status_code == 200
    assert summary(room_code) == after_first

    room_code_2, host_2, players_2 = make_started_room(client)
    yi_2, support_2, before_2 = configure_yi(room_code_2, players_2)
    stale = command(
        client,
        room_code_2,
        host_2,
        host_2["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": yi_2.card_id, "pair_card_ids": [card.card_id for card in support_2]},
        "yi-stale",
        expected_state_version=before_2["state_version"] - 1,
    )
    assert stale.status_code == 400
    assert_unchanged(room_code_2, before_2)
    clear_rooms()


def test_ling_duplicate_action_id_no_double_apply_and_stale_version_rejected():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    ling, before = configure_ling(room_code, players)

    first = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling.card_id}, "ling-repeat", expected_state_version=before["state_version"])
    after_first = summary(room_code)
    replay = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling.card_id}, "ling-repeat", expected_state_version=before["state_version"])

    assert first.status_code == 200
    assert replay.status_code == 200
    assert summary(room_code) == after_first

    room_code_2, host_2, players_2 = make_started_room(client)
    ling_2, before_2 = configure_ling(room_code_2, players_2)
    stale = command(client, room_code_2, host_2, host_2["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling_2.card_id}, "ling-stale", expected_state_version=before_2["state_version"] - 1)
    assert stale.status_code == 400
    assert_unchanged(room_code_2, before_2)
    clear_rooms()
