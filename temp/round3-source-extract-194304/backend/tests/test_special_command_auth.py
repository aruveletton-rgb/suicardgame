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


def make_started_room(client: TestClient, player_count: int = 3):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, player_count):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    ready_all_http(client, host["room_code"], players)
    start = command(client, host["room_code"], host, host["player_id"], "START_GAME", {"seed": 701}, "start")
    assert start.status_code == 200
    return host["room_code"], host, players


def configure_ling_turn(room_code: str, host: dict, guest: dict | None = None):
    ling = special("ling")
    guest_ling = special("ling") if guest is not None else None
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        host_player = room.player(host["player_id"])
        host_player.hand = [ling]
        if guest is not None:
            room.player(guest["player_id"]).hand = [guest_ling]
        game.current_player_id = host_player.player_id
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4")]
        game.current_prompt = None
        game.effect_queue = []
        before = special_state_snapshot(room_code)
    return ling, guest_ling, before


def configure_shop_turn(room_code: str, host: dict, guest: dict):
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        host_player = room.player(host["player_id"])
        guest_player = room.player(guest["player_id"])
        host_payment = uno("uno_red_2")
        guest_payment = uno("uno_blue_2")
        good = uno("uno_red_7")
        host_player.hand = [host_payment]
        guest_player.hand = [guest_payment]
        game.shop.goods = [good]
        game.current_player_id = host_player.player_id
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.current_prompt = None
        game.effect_queue = []
        before = special_state_snapshot(room_code)
    return host_payment, guest_payment, good, before


def special_state_snapshot(room_code: str):
    room = main.rooms[room_code]
    game = room.active_game
    assert game is not None
    return {
        "phase": room.phase.value,
        "state_version": room.state_version,
        "current_player_id": game.current_player_id,
        "prompt_id": game.current_prompt.prompt_id if game.current_prompt else None,
        "effect_count": len(game.effect_queue),
        "shop_good_ids": [card.card_id for card in game.shop.goods],
        "discard_count": len(game.discard_pile),
        "hands": {player.player_id: [card.card_id for card in player.hand] for player in room.players},
    }


def assert_unchanged(room_code: str, before) -> None:
    with main.rooms_lock:
        assert special_state_snapshot(room_code) == before


def test_activate_special_http_requires_valid_session_without_side_effects():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client)
    ling, _guest_ling, before = configure_ling_turn(room_code, host)

    missing = command(client, room_code, None, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling.card_id}, "missing-special")
    invalid = command(client, room_code, {**host, "session_id": "invalid-session"}, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling.card_id}, "invalid-special")

    assert missing.status_code in {401, 403}
    assert invalid.status_code in {401, 403}
    assert_unchanged(room_code, before)
    clear_rooms()


def test_activate_special_rejects_http_player_id_spoof_and_non_current_player():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]
    host_ling, guest_ling, before = configure_ling_turn(room_code, host, guest)

    spoof = command(client, room_code, guest, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": host_ling.card_id}, "guest-spoof-special")
    non_current = command(client, room_code, guest, guest["player_id"], "ACTIVATE_SPECIAL", {"card_id": guest_ling.card_id}, "guest-own-special")

    assert spoof.status_code in {401, 403}
    assert non_current.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_activate_special_websocket_rejects_player_id_spoof_without_mutation():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]
    ling, _guest_ling, before = configure_ling_turn(room_code, host, guest)

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={guest['player_id']}&session_id={guest['session_id']}") as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        websocket.send_json(
            {
                "event": "command",
                "action_id": "ws-spoof-special",
                "player_id": host["player_id"],
                "command_type": "ACTIVATE_SPECIAL",
                "payload": {"card_id": ling.card_id},
            }
        )
        error = websocket.receive_json()
        assert error["event"] == "error"
        assert error["error"] == "AUTH_PLAYER_MISMATCH"
        assert_unchanged(room_code, before)

    clear_rooms()


def test_buy_shop_good_requires_auth_and_rejects_identity_or_turn_spoof():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]
    host_payment, guest_payment, good, before = configure_shop_turn(room_code, host, guest)
    payload = {"good_card_id": good.card_id, "payment_card_id": host_payment.card_id}

    missing = command(client, room_code, None, host["player_id"], "BUY_SHOP_GOOD", payload, "missing-buy")
    invalid = command(client, room_code, {**host, "session_id": "invalid-session"}, host["player_id"], "BUY_SHOP_GOOD", payload, "invalid-buy")
    spoof = command(client, room_code, guest, host["player_id"], "BUY_SHOP_GOOD", payload, "spoof-buy")
    non_current = command(
        client,
        room_code,
        guest,
        guest["player_id"],
        "BUY_SHOP_GOOD",
        {"good_card_id": good.card_id, "payment_card_id": guest_payment.card_id},
        "guest-buy",
    )

    assert missing.status_code in {401, 403}
    assert invalid.status_code in {401, 403}
    assert spoof.status_code in {401, 403}
    assert non_current.status_code == 400
    assert_unchanged(room_code, before)
    clear_rooms()


def test_refresh_shop_http_and_websocket_auth_bindings_reject_spoofing():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]
    _host_payment, _guest_payment, _good, before = configure_shop_turn(room_code, host, guest)

    missing = command(client, room_code, None, host["player_id"], "REFRESH_SHOP", {}, "missing-refresh")
    invalid = command(client, room_code, {**host, "session_id": "invalid-session"}, host["player_id"], "REFRESH_SHOP", {}, "invalid-refresh")
    spoof = command(client, room_code, guest, host["player_id"], "REFRESH_SHOP", {}, "spoof-refresh")
    non_current = command(client, room_code, guest, guest["player_id"], "REFRESH_SHOP", {}, "guest-refresh")

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={guest['player_id']}&session_id={guest['session_id']}") as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"
        websocket.send_json(
            {
                "event": "command",
                "action_id": "ws-spoof-refresh",
                "player_id": host["player_id"],
                "command_type": "REFRESH_SHOP",
                "payload": {},
            }
        )
        ws_error = websocket.receive_json()
        assert ws_error["event"] == "error"
        assert ws_error["error"] == "AUTH_PLAYER_MISMATCH"
        assert_unchanged(room_code, before)

    assert missing.status_code in {401, 403}
    assert invalid.status_code in {401, 403}
    assert spoof.status_code in {401, 403}
    assert non_current.status_code == 400
    clear_rooms()
