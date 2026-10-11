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


def open_yu_prompt(client: TestClient, room_code: str, host: dict):
    yu = special("yu")
    payment = [uno("uno_red_1"), uno("uno_yellow_2"), uno("uno_green_3"), uno("uno_blue_4")]
    reset_game_state(room_code, host["player_id"])
    with main.rooms_lock:
        main.rooms[room_code].player(host["player_id"]).hand = [yu, *payment]
    response = command(
        client,
        room_code,
        host,
        host["player_id"],
        "ACTIVATE_SPECIAL",
        {"card_id": yu.card_id, "payment_card_ids": [item.card_id for item in payment]},
        "open-yu",
    )
    assert response.status_code == 200
    return payment


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
    open_yu_prompt(client, room_code, host)

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
    payment = open_yu_prompt(client, room_code_3, host_3)
    yu_effect = pending_effect(room_code_3)
    assert "card_ids" not in yu_effect
    assert "hands" not in yu_effect
    assert all(card.card_id not in str(yu_effect) for card in payment)
    clear_rooms()


def test_chongyue_selective_display_exposes_only_selected_faces_and_private_candidates():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]
    open_chongyue_prompt(client, room_code, host, players)
    with main.rooms_lock:
        room = main.rooms[room_code]
        selected = list(room.player(guest["player_id"]).hand)
        hidden = uno("uno_red_9")
        room.player(guest["player_id"]).hand.append(hidden)
        prompt_id = room.active_game.current_prompt.prompt_id
        public = main._public_snapshot(room)["state"]["active_game"]["pending_action"]
        private = main._private_snapshot(room, guest["player_id"])["state"]["active_game"]["pending_action"]
        assert public.get("private_option_card_ids", []) == []
        assert set(private["private_option_card_ids"]) == {card.card_id for card in selected}
    response = command(client, room_code, guest, guest["player_id"], "RESPOND_TO_PROMPT", {
        "prompt_id": prompt_id, "response": "submit_cards", "card_ids": [card.card_id for card in selected],
    }, "show-four")
    assert response.status_code == 200
    with main.rooms_lock:
        public_state = main._public_snapshot(main.rooms[room_code])["state"]
        effect = public_state["active_game"]["pending_action"]["effect"]
        shown = effect["displayed_cards"][guest["player_id"]]
        assert {card["card_id"] for card in shown} == {card.card_id for card in selected}
        assert all(card["asset_key"] and card["color"] for card in shown)
        assert hidden.card_id not in str(public_state)
        assert not any(effect["displayed_cards"][player["player_id"]] for player in (players[0], players[2]))
        assert_public_state_has_no_full_hands(public_state)
    clear_rooms()


def test_invalid_websocket_session_gets_no_special_prompt_or_private_snapshot():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, _players = make_started_room(client)
    open_yu_prompt(client, room_code, host)

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={host['player_id']}&session_id=invalid-session") as websocket:
            websocket.receive_json()
    clear_rooms()


def test_reconnect_private_snapshot_during_special_prompt_is_scoped_to_reconnecting_player():
    clear_rooms()
    client = TestClient(main.app)
    room_code, host, players = make_started_room(client)
    guest = players[1]
    open_yu_prompt(client, room_code, host)

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
