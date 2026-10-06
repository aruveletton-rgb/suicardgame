from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main
from backend.tests.ready_helpers import ready_all_http
from backend.app.domain.cards import Card, SPECIAL_BY_KIND, build_core_uno_deck
from backend.app.engine.command_handler import Command, PROCESSED_ACTIONS_LIMIT, process_command


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
    ready_all_http(client, host["room_code"], players)
    start = command(client, host["room_code"], host, host["player_id"], "START_GAME", {"seed": 703}, "start")
    assert start.status_code == 200
    return host["room_code"], host, players


def configure_ling_turn(room_code: str, host: dict):
    ling = special("ling")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        host_player = room.player(host["player_id"])
        host_player.hand = [ling]
        for index, member in enumerate(room.players[1:], start=1):
            member.hand = [uno("uno_red_1"), uno("uno_blue_2"), uno("uno_green_3")][:index]
        game.current_player_id = host_player.player_id
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4")]
        game.current_prompt = None
        game.effect_queue = []
    return ling


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
        game = main.rooms[room_code].active_game
        assert game is not None and game.current_prompt is not None
        return game.current_prompt.prompt_id


def configure_shop_turn(room_code: str, host: dict):
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        host_player = room.player(host["player_id"])
        payment = uno("uno_red_2")
        good = uno("uno_red_7")
        host_player.hand = [payment]
        game.shop.goods = [good]
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4"), uno("uno_blue_5"), uno("uno_green_6"), uno("uno_yellow_7"), uno("uno_red_8")]
        game.shop.bought_this_turn_by.clear()
        game.shop.refreshed_this_turn_by.clear()
        game.current_player_id = host_player.player_id
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.current_prompt = None
        game.effect_queue = []
    return payment, good


def state_summary(room_code: str):
    room = main.rooms[room_code]
    game = room.active_game
    assert game is not None
    return {
        "state_version": room.state_version,
        "current_player_id": game.current_player_id,
        "prompt_id": game.current_prompt.prompt_id if game.current_prompt else None,
        "effect_count": len(game.effect_queue),
        "deck_ids": [card.card_id for card in game.deck],
        "discard_ids": [card.card_id for card in game.discard_pile],
        "shop_good_ids": [card.card_id for card in game.shop.goods],
        "bought": sorted(game.shop.bought_this_turn_by),
        "refreshed": sorted(game.shop.refreshed_this_turn_by),
        "hands": {player.player_id: [card.card_id for card in player.hand] for player in room.players},
    }


def test_activate_special_duplicate_action_id_and_stale_version_are_safe():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client)
    ling = configure_ling_turn(room_code, host)
    with main.rooms_lock:
        current_version = main.rooms[room_code].state_version

    accepted = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": ling.card_id},
        "activate-ling-once",
        expected_state_version=current_version,
    )
    after_first = state_summary(room_code)
    replay = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": ling.card_id},
        "activate-ling-once",
        expected_state_version=current_version,
    )
    after_replay = state_summary(room_code)

    room_code_2, host_2, _players_2 = make_started_room(client)
    stale_ling = configure_ling_turn(room_code_2, host_2)
    stale_version = main.rooms[room_code_2].state_version - 1
    before_stale = state_summary(room_code_2)
    stale = command(
        client,
        room_code_2,
        host_2,
        host_2["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": stale_ling.card_id},
        "activate-stale",
        expected_state_version=stale_version,
    )

    assert accepted.status_code == 200
    assert replay.status_code == 200
    assert after_replay == after_first
    assert stale.status_code == 400
    assert state_summary(room_code_2) == before_stale
    clear_rooms()


def test_respond_to_prompt_duplicate_action_id_and_stale_version_are_safe():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    prompt_id = open_ji_prompt(client, room_code, host)
    responder = players[1]
    with main.rooms_lock:
        current_version = main.rooms[room_code].state_version

    accepted = command(
        client,
        room_code,
        responder,
        responder["player_id"],
        "RESPOND_TO_PROMPT",
        {"prompt_id": prompt_id, "response": "pass"},
        "respond-once",
        expected_state_version=current_version,
    )
    after_first = state_summary(room_code)
    replay = command(
        client,
        room_code,
        responder,
        responder["player_id"],
        "RESPOND_TO_PROMPT",
        {"prompt_id": prompt_id, "response": "pass"},
        "respond-once",
        expected_state_version=current_version,
    )

    room_code_2, host_2, players_2 = make_started_room(client)
    stale_prompt_id = open_ji_prompt(client, room_code_2, host_2)
    stale_responder = players_2[1]
    stale_version = main.rooms[room_code_2].state_version - 1
    before_stale = state_summary(room_code_2)
    stale = command(
        client,
        room_code_2,
        stale_responder,
        stale_responder["player_id"],
        "RESPOND_TO_PROMPT",
        {"prompt_id": stale_prompt_id, "response": "pass"},
        "respond-stale",
        expected_state_version=stale_version,
    )

    assert accepted.status_code == 200
    assert replay.status_code == 200
    assert state_summary(room_code) == after_first
    assert stale.status_code == 400
    assert state_summary(room_code_2) == before_stale
    clear_rooms()


def test_buy_shop_good_duplicate_action_id_and_stale_version_are_safe():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client)
    payment, good = configure_shop_turn(room_code, host)
    with main.rooms_lock:
        current_version = main.rooms[room_code].state_version

    accepted = command(
        client,
        room_code,
        host,
        host["player_id"],
        "BUY_SHOP_GOOD",
        {"good_card_id": good.card_id, "payment_card_id": payment.card_id},
        "buy-once",
        expected_state_version=current_version,
    )
    after_first = state_summary(room_code)
    replay = command(
        client,
        room_code,
        host,
        host["player_id"],
        "BUY_SHOP_GOOD",
        {"good_card_id": good.card_id, "payment_card_id": payment.card_id},
        "buy-once",
        expected_state_version=current_version,
    )

    room_code_2, host_2, _players_2 = make_started_room(client)
    stale_payment, stale_good = configure_shop_turn(room_code_2, host_2)
    stale_version = main.rooms[room_code_2].state_version - 1
    before_stale = state_summary(room_code_2)
    stale = command(
        client,
        room_code_2,
        host_2,
        host_2["player_id"],
        "BUY_SHOP_GOOD",
        {"good_card_id": stale_good.card_id, "payment_card_id": stale_payment.card_id},
        "buy-stale",
        expected_state_version=stale_version,
    )

    assert accepted.status_code == 200
    assert replay.status_code == 200
    assert state_summary(room_code) == after_first
    assert stale.status_code == 400
    assert state_summary(room_code_2) == before_stale
    clear_rooms()


def test_refresh_shop_duplicate_action_id_once_per_turn_and_stale_version_are_safe():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client)
    configure_shop_turn(room_code, host)
    with main.rooms_lock:
        current_version = main.rooms[room_code].state_version

    accepted = command(client, room_code, host, host["player_id"], "REFRESH_SHOP", {}, "refresh-once", expected_state_version=current_version)
    after_first = state_summary(room_code)
    replay = command(client, room_code, host, host["player_id"], "REFRESH_SHOP", {}, "refresh-once", expected_state_version=current_version)
    second_refresh = command(client, room_code, host, host["player_id"], "REFRESH_SHOP", {}, "refresh-again")

    room_code_2, host_2, _players_2 = make_started_room(client)
    configure_shop_turn(room_code_2, host_2)
    stale_version = main.rooms[room_code_2].state_version - 1
    before_stale = state_summary(room_code_2)
    stale = command(client, room_code_2, host_2, host_2["player_id"], "REFRESH_SHOP", {}, "refresh-stale", expected_state_version=stale_version)

    assert accepted.status_code == 200
    assert replay.status_code == 200
    assert second_refresh.status_code == 400
    assert state_summary(room_code) == after_first
    assert stale.status_code == 400
    assert state_summary(room_code_2) == before_stale
    clear_rooms()


def test_processed_actions_keeps_recent_idempotency_window_bounded():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client)
    room = main.rooms[room_code]
    latest_response = None
    for index in range(300):
        latest_response = process_command(room, Command(
            action_id=f"bounded-ready-{index}",
            room_id=room_code,
            player_id=host["player_id"],
            command_type="READY",
            payload={"ready": True},
        ))

    before_replay = room.state_version
    replay = process_command(room, Command(
        action_id="bounded-ready-299",
        room_id=room_code,
        player_id=host["player_id"],
        command_type="READY",
        payload={"ready": True},
    ))

    assert len(room.processed_actions) <= PROCESSED_ACTIONS_LIMIT
    assert "bounded-ready-299" in room.processed_actions
    assert "bounded-ready-0" not in room.processed_actions
    assert replay == latest_response
    assert room.state_version == before_replay
    clear_rooms()
