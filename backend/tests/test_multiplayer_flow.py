from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.domain.cards import build_core_uno_deck


def clear_rooms() -> None:
    with main.rooms_lock:
        main.rooms.clear()


def card(asset_key):
    return next(item for item in build_core_uno_deck() if item.asset_key == asset_key)


def auth_header(session):
    return {"Authorization": f"Bearer {session['session_id']}"}


def command(client, room_code, session, command_type, payload=None, action_id=None, player_id=None):
    player_id = player_id or session["player_id"]
    body = {
        "action_id": action_id or f"{command_type}-{player_id}",
        "player_id": player_id,
        "command_type": command_type,
        "payload": payload or {},
    }
    return client.post(f"/api/v1/rooms/{room_code}/commands", json=body, headers=auth_header(session))


def test_two_player_flow_broadcasts_play_draw_and_reconnects():
    clear_rooms()
    client = TestClient(main.app)
    host = client.post("/api/v1/rooms", json={"nickname": "host"}).json()
    guest = client.post(f"/api/v1/rooms/{host['room_code']}/join", json={"nickname": "guest"}).json()
    room_code = host["room_code"]

    assert command(client, room_code, host, "READY", {"ready": True}, "ready-host").status_code == 200
    assert command(client, room_code, guest, "READY", {"ready": True}, "ready-guest").status_code == 200
    assert command(client, room_code, host, "START_GAME", {"seed": 9}, "start-game").status_code == 200

    room = main.rooms[room_code]
    red_7 = card("uno_red_7")
    with room.lock:
        game = room.active_game
        assert game is not None
        host_player = room.player(host["player_id"])
        guest_player = room.player(guest["player_id"])
        host_player.hand = [red_7, card("uno_blue_9")]
        guest_player.hand = []
        game.discard_pile = [card("uno_red_5")]
        game.current_color = game.discard_pile[-1].color
        game.deck = [card("uno_green_3")]
        game.current_player_id = host_player.player_id
        game.current_prompt = None

    with client.websocket_connect(f"/api/v1/rooms/{room_code}/ws?player_id={guest['player_id']}&session_id={guest['session_id']}") as websocket:
        assert websocket.receive_json()["event"] == "snapshot"
        assert websocket.receive_json()["event"] == "private_snapshot"

        play_response = command(
            client,
            room_code,
            host,
            "PLAY_CARD",
            {"card_id": red_7.card_id},
            "host-plays-red-7",
        )
        assert play_response.status_code == 200
        play_patch = websocket.receive_json()
        assert play_patch["event"] == "state_patch"
        assert play_patch["state"]["active_game"]["current_player_id"] == host["player_id"]
        prompt = play_patch["state"]["active_game"]["pending_action"]
        assert prompt["kind"] == "HAS_SUI_CHALLENGE"
        host_public = next(player for player in play_patch["state"]["players"] if player["player_id"] == host["player_id"])
        assert host_public["hand_count"] == 1
        assert websocket.receive_json()["event"] == "private_snapshot"

        decline_play = command(
            client,
            room_code,
            guest,
            "RESPOND_TO_PROMPT",
            {"prompt_id": prompt["prompt_id"], "response": "decline_challenge"},
            "guest-declines-host-has-sui",
        )
        assert decline_play.status_code == 200
        decline_patch = websocket.receive_json()
        assert decline_patch["event"] == "state_patch"
        assert decline_patch["state"]["active_game"]["current_player_id"] == guest["player_id"]
        assert websocket.receive_json()["event"] == "private_snapshot"

        draw_response = command(client, room_code, guest, "DRAW_CARD", {}, "guest-draws")
        assert draw_response.status_code == 200
        draw_patch = websocket.receive_json()
        assert draw_patch["event"] == "state_patch"
        assert draw_patch["state"]["active_game"]["current_player_id"] == guest["player_id"]
        draw_prompt = draw_patch["state"]["active_game"]["pending_action"]
        assert draw_prompt["kind"] == "HAS_SUI_CHALLENGE"
        guest_public = next(player for player in draw_patch["state"]["players"] if player["player_id"] == guest["player_id"])
        assert guest_public["hand_count"] == 1
        assert websocket.receive_json()["event"] == "private_snapshot"

        decline_draw = command(
            client,
            room_code,
            host,
            "RESPOND_TO_PROMPT",
            {"prompt_id": draw_prompt["prompt_id"], "response": "decline_challenge"},
            "host-declines-guest-has-sui",
        )
        assert decline_draw.status_code == 200
        after_draw_patch = websocket.receive_json()
        assert after_draw_patch["event"] == "state_patch"
        assert after_draw_patch["state"]["active_game"]["current_player_id"] == host["player_id"]
        assert websocket.receive_json()["event"] == "private_snapshot"

    reconnect = client.post(
        f"/api/v1/rooms/{room_code}/reconnect",
        json={"player_id": host["player_id"], "reconnect_token": host["reconnect_token"]},
    )
    assert reconnect.status_code == 200
    body = reconnect.json()
    assert body["private_snapshot"]["you"]["player_id"] == host["player_id"]
    assert len(body["private_snapshot"]["you"]["hand"]) == 1
    assert body["reconnect_token"] != host["reconnect_token"]
    clear_rooms()
