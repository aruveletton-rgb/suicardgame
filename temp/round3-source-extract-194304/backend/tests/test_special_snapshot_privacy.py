from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import backend.app.main as main
from backend.tests.ready_helpers import pass_sui_activation_reactions, ready_all_http
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


def make_started_room(client: TestClient, player_count: int = 3):
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    players = [host]
    for index in range(1, player_count):
        players.append(client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": f"p{index}"}).json())
    ready_all_http(client, host["room_code"], players)
    start = command(client, host["room_code"], host, host["player_id"], "START_GAME", {"seed": 704}, "start")
    assert start.status_code == 200
    return host["room_code"], host, players


def reset_game_state(room_code: str, current_player_id: str):
    with main.rooms_lock:
        room = main.rooms[room_code]
        game = room.active_game
        assert game is not None
        game.current_player_id = current_player_id
        game.discard_pile = [uno("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [uno("uno_blue_1"), uno("uno_green_2"), uno("uno_yellow_3"), uno("uno_red_4"), uno("uno_blue_5"), uno("uno_green_6")]
        game.current_prompt = None
        game.effect_queue = []
        game.reveal_area = []


def open_ji_prompt(client: TestClient, room_code: str, host: dict):
    ji = special("ji")
    reset_game_state(room_code, host["player_id"])
    with main.rooms_lock:
        main.rooms[room_code].player(host["player_id"]).hand = [ji, uno("uno_red_1")]
    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": ji.card_id, "chosen_color": "red"}, "open-ji")
    assert response.status_code == 200
    with main.rooms_lock:
        pass_sui_activation_reactions(main.rooms[room_code], action_prefix="privacy-ji-reaction")


def open_chongyue_prompt(client: TestClient, room_code: str, host: dict, players: list[dict]):
    chongyue = special("chongyue")
    reset_game_state(room_code, host["player_id"])
    colors = [uno("uno_red_1"), uno("uno_yellow_2"), uno("uno_green_3"), uno("uno_blue_4")]
    with main.rooms_lock:
        room = main.rooms[room_code]
        room.player(host["player_id"]).hand = [chongyue, *colors]
        for player in players[1:]:
            room.player(player["player_id"]).hand = [uno("uno_red_2"), uno("uno_yellow_3"), uno("uno_green_4"), uno("uno_blue_5")]
    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": chongyue.card_id}, "open-chongyue")
    assert response.status_code == 200
    with main.rooms_lock:
        pass_sui_activation_reactions(main.rooms[room_code], action_prefix="privacy-chongyue-reaction")


def open_wang_prompt(client: TestClient, room_code: str, host: dict, guest: dict):
    wang = special("wang")
    reset_game_state(room_code, guest["player_id"])
    with main.rooms_lock:
        room = main.rooms[room_code]
        room.player(host["player_id"]).hand = [wang]
        room.player(guest["player_id"]).hand = [uno("uno_blue_9")]
    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": wang.card_id, "target_player_id": guest["player_id"]},
        "open-wang",
    )
    assert response.status_code == 200
    with main.rooms_lock:
        pass_sui_activation_reactions(main.rooms[room_code], action_prefix="privacy-wang-reaction")


def open_fuzhou_prompt(client: TestClient, room_code: str, host: dict, guest: dict):
    fuzhou = special("fuzhou")
    reset_game_state(room_code, host["player_id"])
    with main.rooms_lock:
        room = main.rooms[room_code]
        room.player(host["player_id"]).hand = [fuzhou]
        room.player(guest["player_id"]).hand = [uno("uno_green_3")]
    response = command(client, room_code, host, host["player_id"], "ACTIVATE_SPECIAL", {"card_id": fuzhou.card_id}, "open-fuzhou")
    assert response.status_code == 200
    with main.rooms_lock:
        pass_sui_activation_reactions(main.rooms[room_code], action_prefix="privacy-fuzhou-reaction")


def assert_public_state_has_no_full_hands(state: dict) -> None:
    assert all("hand" not in player for player in state["players"])


def pending_effect(room_code: str):
    state = main._public_snapshot(main.rooms[room_code])["state"]
    assert state["active_game"] is not None
    return state["active_game"]["pending_action"]["effect"]


def test_public_snapshot_and_private_snapshot_keep_full_hands_scoped_to_authenticated_player():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]
    open_ji_prompt(client, room_code, host)

    with main.rooms_lock:
        public = main._public_snapshot(main.rooms[room_code])
        private = main._private_snapshot(main.rooms[room_code], guest["player_id"])

    assert_public_state_has_no_full_hands(public["state"])
    assert_public_state_has_no_full_hands(private["state"])
    assert private["you"]["player_id"] == guest["player_id"]
    assert "hand" in private["you"]
    assert all("hand" not in player for player in private["state"]["players"])
    clear_rooms()


def test_special_prompt_payloads_do_not_expose_full_hand_card_payloads():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)

    open_chongyue_prompt(client, room_code, host, players)
    chongyue_effect = pending_effect(room_code)
    assert "displayed_colors" in chongyue_effect
    assert "card_ids" not in chongyue_effect
    assert "hands" not in chongyue_effect
    assert all(isinstance(colors, list) for colors in chongyue_effect["displayed_colors"].values())

    room_code_2, host_2, players_2 = make_started_room(client)
    open_wang_prompt(client, room_code_2, host_2, players_2[1])
    wang_effect = pending_effect(room_code_2)
    assert set(wang_effect) <= {"type", "source_card_kind", "source_player_id", "controlled_player_id", "immune_player_ids"}

    room_code_3, host_3, players_3 = make_started_room(client)
    open_fuzhou_prompt(client, room_code_3, host_3, players_3[1])
    fuzhou_effect = pending_effect(room_code_3)
    assert set(fuzhou_effect) <= {"type", "source_card_kind", "source_player_id", "immune_player_ids", "responder_index"}
    clear_rooms()


def test_invalid_websocket_session_gets_no_special_prompt_or_private_snapshot():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client)
    open_ji_prompt(client, room_code, host)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id=invalid-session") as websocket:
            websocket.receive_json()
    clear_rooms()


def test_reconnect_private_snapshot_during_special_prompt_is_scoped_to_reconnecting_player():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]
    open_fuzhou_prompt(client, room_code, host, guest)

    reconnect = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": guest["player_id"], "reconnect_token": guest["reconnect_token"]},
    )
    assert reconnect.status_code == 200
    private = reconnect.json()["private_snapshot"]

    assert private["you"]["player_id"] == guest["player_id"]
    assert "hand" in private["you"]
    assert_public_state_has_no_full_hands(private["state"])
    assert all("hand" not in player for player in private["state"]["players"])
    clear_rooms()
