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


def command(client: TestClient, room_code: str, session: dict, player_id: str, command_type: str, payload=None, action_id="cmd"):
    return client.post(
        f"/api/v1/rooms/{room_code}/commands",
        json={"action_id": action_id, "player_id": player_id, "command_type": command_type, "payload": payload or {}},
        headers=auth_header(session),
    )


def make_started_room(client: TestClient):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, 3):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    ready_all_http(client, host["room_code"], players)
    start = command(client, host["room_code"], host, host["player_id"], "START_GAME", {"seed": 808}, "start")
    assert start.status_code == 200
    return host["room_code"], host, players


def assert_public_state_has_no_full_hands(state: dict) -> None:
    assert all("hand" not in player for player in state["players"])
    assert all("hand_count" in player for player in state["players"])


def configure_and_activate_yi(client: TestClient, room_code: str, host: dict, players: list[dict]):
    yi = special("yi")
    three = uno("uno_red_3")
    five = uno("uno_blue_5")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        room.player(host["player_id"]).hand = [yi, three, five, uno("uno_yellow_9")]
        room.player(players[1]["player_id"]).hand = [uno("uno_green_1")]
        room.player(players[2]["player_id"]).hand = [uno("uno_yellow_2")]
        game.current_player_id = host["player_id"]
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4")]
        game.current_prompt = None
        game.effect_queue = []
    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": yi.card_id, "pair_card_ids": [three.card_id, five.card_id]}, "yi-snapshot")
    assert response.status_code == 200


def configure_and_activate_ling(client: TestClient, room_code: str, host: dict, players: list[dict]):
    ling = special("ling")
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        room.player(host["player_id"]).hand = [ling, uno("uno_red_1")]
        room.player(players[1]["player_id"]).hand = [uno("uno_red_2"), uno("uno_blue_3"), uno("uno_green_4")]
        room.player(players[2]["player_id"]).hand = [uno("uno_green_1")]
        game.current_player_id = host["player_id"]
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4"), uno("uno_blue_6"), uno("uno_yellow_7")]
        game.current_prompt = None
        game.effect_queue = []
    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ling.card_id}, "ling-snapshot")
    assert response.status_code == 200


def assert_private_snapshot_scoped(room_code: str, player_id: str) -> None:
    with main.rooms_lock:
        private = main._private_snapshot(main.rooms[room_code], player_id)
    assert_public_state_has_no_full_hands(private["state"])
    assert private["you"]["player_id"] == player_id
    assert "hand" in private["you"]
    assert all("hand" not in player for player in private["state"]["players"])


def test_yi_snapshot_privacy_public_no_full_hands_private_own_hand_only():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    configure_and_activate_yi(client, room_code, host, players)

    with main.rooms_lock:
        public = main._public_snapshot(main.rooms[room_code])
    assert_public_state_has_no_full_hands(public["state"])
    assert_private_snapshot_scoped(room_code, host["player_id"])
    assert_private_snapshot_scoped(room_code, players[1]["player_id"])
    clear_rooms()


def test_ling_snapshot_privacy_public_no_full_hands_private_own_hand_only():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    configure_and_activate_ling(client, room_code, host, players)

    with main.rooms_lock:
        public = main._public_snapshot(main.rooms[room_code])
    assert_public_state_has_no_full_hands(public["state"])
    assert_private_snapshot_scoped(room_code, host["player_id"])
    assert_private_snapshot_scoped(room_code, players[2]["player_id"])
    clear_rooms()
